package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

internal data class GitHubDeviceCode(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val expiresInSeconds: Long,
    val intervalSeconds: Long,
)

internal data class GitHubOwnerCredential(
    val accessToken: String,
    val accessTokenExpiresAtEpochSeconds: Long?,
    val refreshToken: String?,
    val refreshTokenExpiresAtEpochSeconds: Long?,
)

internal data class GitHubOwnerIdentity(
    val credential: GitHubOwnerCredential,
    val session: OwnerAccessSession,
) {
    val accessToken: String get() = credential.accessToken
}

internal class GitHubOwnerAuthenticationException(
    val reason: String,
) : RuntimeException(reason)

/**
 * GitHub App Device Flow for the Source Lab owner session.
 *
 * The first sign-in remains interactive. Afterwards the token pair can be kept
 * in the Android-Keystore-backed credential vault and refreshed silently. The
 * owner identity, exact GitHub App installation and repository permissions are
 * revalidated every time a saved credential is restored.
 */
internal object GitHubOwnerAuthentication {
    private const val deviceCodeEndpoint = "https://github.com/login/device/code"
    private const val tokenEndpoint = "https://github.com/login/oauth/access_token"
    private const val apiBase = "https://api.github.com"
    private const val refreshEarlySeconds = 120L

    internal fun resolveClientId(): String {
        val embedded = BuildConfig.SOURCE_LAB_GITHUB_CLIENT_ID.trim()
        validateClientId(embedded)
        return embedded
    }

    internal fun isValidClientId(clientId: String): Boolean = try {
        validateClientId(clientId)
        true
    } catch (_: GitHubOwnerAuthenticationException) {
        false
    }

    internal fun validateClientId(clientId: String) {
        val value = clientId.trim()
        if (value.isBlank()) {
            throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_NOT_CONFIGURED")
        }
        if (value == SourceLabAccessPolicy.installationId.toString()) {
            throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_IS_INSTALLATION_ID")
        }
        if (value == SourceLabAccessPolicy.githubAppId.toString()) {
            throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_IS_APP_ID")
        }
        if (value.all(Char::isDigit)) {
            throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_MUST_NOT_BE_NUMERIC")
        }
        if (!value.matches(Regex("[A-Za-z0-9._-]{10,128}"))) {
            throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_FORMAT_INVALID")
        }
    }

    suspend fun requestDeviceCode(clientId: String): GitHubDeviceCode =
        withContext(Dispatchers.IO) {
            val normalizedClientId = clientId.trim()
            validateClientId(normalizedClientId)

            val payload = formPost(
                url = deviceCodeEndpoint,
                fields = mapOf("client_id" to normalizedClientId),
            )
            val json = JSONObject(payload)
            val error = json.optString("error").takeIf { it.isNotBlank() }
            if (error != null) {
                val reason = when (error) {
                    "incorrect_client_credentials" -> "GITHUB_CLIENT_ID_INVALID"
                    else -> "DEVICE_CODE_${error.uppercase()}"
                }
                throw GitHubOwnerAuthenticationException(reason)
            }

            val deviceCode = json.optString("device_code")
            val userCode = json.optString("user_code")
            val verificationUri = json.optString("verification_uri")
            val expiresIn = json.optLong("expires_in", 0L)
            val interval = json.optLong("interval", 5L).coerceAtLeast(5L)
            if (deviceCode.isBlank() || userCode.isBlank() || verificationUri.isBlank() || expiresIn <= 0L) {
                throw GitHubOwnerAuthenticationException("DEVICE_CODE_RESPONSE_INVALID")
            }

            GitHubDeviceCode(
                deviceCode = deviceCode,
                userCode = userCode,
                verificationUri = verificationUri,
                expiresInSeconds = expiresIn,
                intervalSeconds = interval,
            )
        }

    suspend fun completeOwnerLogin(
        clientId: String,
        deviceCode: GitHubDeviceCode,
    ): GitHubOwnerIdentity = withContext(Dispatchers.IO) {
        val credential = pollForToken(clientId.trim(), deviceCode)
        val session = validateOwnerSession(credential.accessToken)
        GitHubOwnerIdentity(credential = credential, session = session)
    }

    suspend fun restoreOwnerLogin(
        clientId: String,
        storedCredential: GitHubOwnerCredential,
    ): GitHubOwnerIdentity = withContext(Dispatchers.IO) {
        val normalizedClientId = clientId.trim()
        validateClientId(normalizedClientId)
        val now = System.currentTimeMillis() / 1000L

        var credential = storedCredential
        if (credentialNeedsRefresh(credential, now)) {
            credential = refreshCredential(normalizedClientId, credential, now)
        }

        val session = try {
            validateOwnerSession(credential.accessToken)
        } catch (error: GitHubOwnerAuthenticationException) {
            if (error.reason != "GITHUB_IDENTITY_UNAUTHORIZED" || !canRefresh(credential, now)) {
                throw error
            }
            credential = refreshCredential(normalizedClientId, credential, now)
            validateOwnerSession(credential.accessToken)
        }

        GitHubOwnerIdentity(credential = credential, session = session)
    }

    internal fun credentialNeedsRefresh(
        credential: GitHubOwnerCredential,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000L,
    ): Boolean {
        val expiresAt = credential.accessTokenExpiresAtEpochSeconds ?: return false
        return expiresAt <= nowEpochSeconds + refreshEarlySeconds
    }

    internal fun parseTokenCredentialResponse(
        json: JSONObject,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000L,
    ): GitHubOwnerCredential {
        val accessToken = json.optString("access_token").trim()
        if (accessToken.isBlank()) {
            throw GitHubOwnerAuthenticationException("DEVICE_TOKEN_RESPONSE_INVALID")
        }
        val expiresIn = json.optLong("expires_in", 0L).takeIf { it > 0L }
        val refreshToken = json.optString("refresh_token").trim().takeIf { it.isNotEmpty() }
        val refreshExpiresIn = json.optLong("refresh_token_expires_in", 0L).takeIf { it > 0L }
        return GitHubOwnerCredential(
            accessToken = accessToken,
            accessTokenExpiresAtEpochSeconds = expiresIn?.let { nowEpochSeconds + it },
            refreshToken = refreshToken,
            refreshTokenExpiresAtEpochSeconds = refreshExpiresIn?.let { nowEpochSeconds + it },
        )
    }

    private suspend fun pollForToken(
        clientId: String,
        code: GitHubDeviceCode,
    ): GitHubOwnerCredential {
        validateClientId(clientId)

        val deadline = System.currentTimeMillis() + code.expiresInSeconds * 1_000L
        var intervalMs = code.intervalSeconds * 1_000L
        while (System.currentTimeMillis() < deadline) {
            val payload = formPost(
                url = tokenEndpoint,
                fields = mapOf(
                    "client_id" to clientId,
                    "device_code" to code.deviceCode,
                    "grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
                ),
            )
            val json = JSONObject(payload)
            val accessToken = json.optString("access_token")
            if (accessToken.isNotBlank()) return parseTokenCredentialResponse(json)

            when (val error = json.optString("error")) {
                "authorization_pending" -> Unit
                "slow_down" -> {
                    val serverInterval = json.optLong("interval", 0L)
                    intervalMs = if (serverInterval > 0L) {
                        serverInterval.coerceAtLeast(5L) * 1_000L
                    } else {
                        intervalMs + 5_000L
                    }
                }
                "expired_token" -> throw GitHubOwnerAuthenticationException("DEVICE_CODE_EXPIRED")
                "access_denied" -> throw GitHubOwnerAuthenticationException("DEVICE_CODE_ACCESS_DENIED")
                "incorrect_device_code" -> throw GitHubOwnerAuthenticationException("DEVICE_CODE_INVALID")
                "incorrect_client_credentials" -> throw GitHubOwnerAuthenticationException("GITHUB_CLIENT_ID_INVALID")
                else -> {
                    if (error.isNotBlank()) {
                        throw GitHubOwnerAuthenticationException("DEVICE_FLOW_${error.uppercase()}")
                    }
                    throw GitHubOwnerAuthenticationException("DEVICE_TOKEN_RESPONSE_INVALID")
                }
            }
            delay(intervalMs)
        }
        throw GitHubOwnerAuthenticationException("DEVICE_CODE_EXPIRED")
    }

    private fun refreshCredential(
        clientId: String,
        credential: GitHubOwnerCredential,
        nowEpochSeconds: Long,
    ): GitHubOwnerCredential {
        val refreshToken = credential.refreshToken
            ?.takeIf { it.isNotBlank() }
            ?: throw GitHubOwnerAuthenticationException("GITHUB_SAVED_SESSION_EXPIRED")
        val refreshExpiresAt = credential.refreshTokenExpiresAtEpochSeconds
        if (refreshExpiresAt != null && refreshExpiresAt <= nowEpochSeconds + refreshEarlySeconds) {
            throw GitHubOwnerAuthenticationException("GITHUB_SAVED_SESSION_EXPIRED")
        }

        val json = JSONObject(
            formPost(
                url = tokenEndpoint,
                fields = mapOf(
                    "client_id" to clientId,
                    "grant_type" to "refresh_token",
                    "refresh_token" to refreshToken,
                ),
            ),
        )
        val error = json.optString("error").takeIf { it.isNotBlank() }
        if (error != null) {
            val reason = when (error) {
                "bad_refresh_token", "expired_token" -> "GITHUB_SAVED_SESSION_EXPIRED"
                "incorrect_client_credentials" -> "GITHUB_CLIENT_ID_INVALID"
                else -> "GITHUB_REFRESH_${error.uppercase()}"
            }
            throw GitHubOwnerAuthenticationException(reason)
        }
        return parseTokenCredentialResponse(json, nowEpochSeconds)
    }

    private fun canRefresh(credential: GitHubOwnerCredential, nowEpochSeconds: Long): Boolean {
        if (credential.refreshToken.isNullOrBlank()) return false
        val expiresAt = credential.refreshTokenExpiresAtEpochSeconds ?: return true
        return expiresAt > nowEpochSeconds + refreshEarlySeconds
    }

    private suspend fun validateOwnerSession(accessToken: String): OwnerAccessSession = coroutineScope {
        // These GitHub reads are independent. Run them concurrently so a saved
        // Owner session is bounded by the slowest request instead of four
        // sequential network round-trips.
        val userJob = async(Dispatchers.IO) {
            JSONObject(githubGet("$apiBase/user", accessToken))
        }
        val repositoryJob = async(Dispatchers.IO) {
            JSONObject(githubGet("$apiBase/repos/${SourceLabAccessPolicy.repository}", accessToken))
        }
        val installationsJob = async(Dispatchers.IO) {
            JSONObject(githubGet("$apiBase/user/installations?per_page=100", accessToken))
        }
        val installedRepositoriesJob = async(Dispatchers.IO) {
            JSONObject(
                githubGet(
                    "$apiBase/user/installations/${SourceLabAccessPolicy.installationId}/repositories?per_page=100",
                    accessToken,
                ),
            )
        }

        val user = userJob.await()
        val userId = user.optLong("id", -1L)
        if (userId != SourceLabAccessPolicy.ownerGithubUserId) {
            throw GitHubOwnerAuthenticationException("OWNER_ID_MISMATCH")
        }

        val repository = repositoryJob.await()
        if (repository.optLong("id", -1L) != SourceLabAccessPolicy.repositoryId) {
            throw GitHubOwnerAuthenticationException("REPOSITORY_ID_MISMATCH")
        }
        val permissions = repository.optJSONObject("permissions")
        if (permissions?.optBoolean("admin", false) != true) {
            throw GitHubOwnerAuthenticationException("INSUFFICIENT_REPOSITORY_PERMISSION")
        }

        val installations = installationsJob.await().optJSONArray("installations")
            ?: throw GitHubOwnerAuthenticationException("INSTALLATION_LIST_MISSING")
        var exactInstallationFound = false
        for (index in 0 until installations.length()) {
            val installation = installations.optJSONObject(index) ?: continue
            if (installation.optLong("id", -1L) != SourceLabAccessPolicy.installationId) continue
            if (installation.optLong("app_id", -1L) != SourceLabAccessPolicy.githubAppId) {
                throw GitHubOwnerAuthenticationException("GITHUB_APP_MISMATCH")
            }
            val accountId = installation.optJSONObject("account")?.optLong("id", -1L) ?: -1L
            if (accountId != SourceLabAccessPolicy.ownerGithubUserId) {
                throw GitHubOwnerAuthenticationException("INSTALLATION_ACCOUNT_MISMATCH")
            }
            exactInstallationFound = true
            break
        }
        if (!exactInstallationFound) {
            throw GitHubOwnerAuthenticationException("INSTALLATION_MISMATCH")
        }

        val installedRepositories = installedRepositoriesJob.await().optJSONArray("repositories")
            ?: throw GitHubOwnerAuthenticationException("INSTALLATION_REPOSITORY_LIST_MISSING")
        val exactRepositoryInstalled = (0 until installedRepositories.length()).any { index ->
            installedRepositories.optJSONObject(index)?.optLong("id", -1L) == SourceLabAccessPolicy.repositoryId
        }
        if (!exactRepositoryInstalled) {
            throw GitHubOwnerAuthenticationException("REPOSITORY_NOT_IN_INSTALLATION")
        }

        OwnerAccessSession(
            authenticated = true,
            githubUserId = SourceLabAccessPolicy.ownerGithubUserId,
            githubAppId = SourceLabAccessPolicy.githubAppId,
            installationId = SourceLabAccessPolicy.installationId,
            repository = SourceLabAccessPolicy.repository,
            repositoryPermission = SourceLabAccessPolicy.minimumRepositoryPermission,
            backendAuthorized = false,
        )
    }

    private fun formPost(url: String, fields: Map<String, String>): String {
        val form = fields.entries.joinToString("&") { (key, value) ->
            "${encode(key)}=${encode(value)}"
        }
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 10_000
            readTimeout = 15_000
            useCaches = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1")
        }
        return try {
            connection.outputStream.use { output ->
                output.write(form.toByteArray(StandardCharsets.UTF_8))
            }
            val code = connection.responseCode
            val body = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = body?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val reason = when (code) {
                    404 -> "GITHUB_DEVICE_FLOW_ENDPOINT_NOT_FOUND"
                    429 -> "GITHUB_RATE_LIMITED"
                    else -> "GITHUB_HTTP_$code"
                }
                throw GitHubOwnerAuthenticationException(reason)
            }
            text
        } finally {
            connection.disconnect()
        }
    }

    private fun githubGet(url: String, accessToken: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 15_000
            useCaches = false
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $accessToken")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1")
        }
        return try {
            val code = connection.responseCode
            val body = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = body?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                val reason = when (code) {
                    401 -> "GITHUB_IDENTITY_UNAUTHORIZED"
                    403 -> "GITHUB_IDENTITY_PERMISSION_DENIED"
                    404 -> "GITHUB_IDENTITY_RESOURCE_NOT_FOUND"
                    429 -> "GITHUB_RATE_LIMITED"
                    else -> "GITHUB_HTTP_$code"
                }
                throw GitHubOwnerAuthenticationException(reason)
            }
            text
        } finally {
            connection.disconnect()
        }
    }

    private fun encode(value: String): String =
        URLEncoder.encode(value, StandardCharsets.UTF_8.name())
}
