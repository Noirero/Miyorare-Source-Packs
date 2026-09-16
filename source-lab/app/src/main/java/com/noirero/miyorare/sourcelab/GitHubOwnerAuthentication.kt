package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
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

internal data class GitHubOwnerIdentity(
    val accessToken: String,
    val session: OwnerAccessSession,
)

internal class GitHubOwnerAuthenticationException(
    val reason: String,
) : RuntimeException(reason)

/**
 * Interactive GitHub App Device Flow for the Source Lab owner session.
 *
 * The public GitHub App Client ID is embedded by the official release build.
 * Runtime/manual Client ID overrides are intentionally unsupported so an App ID
 * or Installation ID can never replace the trusted build configuration.
 *
 * The returned user access token is kept in memory only and is never written
 * to SharedPreferences, files, logs, or the APK.
 */
internal object GitHubOwnerAuthentication {
    private const val deviceCodeEndpoint = "https://github.com/login/device/code"
    private const val tokenEndpoint = "https://github.com/login/oauth/access_token"
    private const val apiBase = "https://api.github.com"

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
        // GitHub App Client IDs currently look like `Iv1.ab1112223334445c`.
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
        val token = pollForToken(clientId.trim(), deviceCode)
        val session = validateOwnerSession(token)
        GitHubOwnerIdentity(
            accessToken = token,
            session = session,
        )
    }

    private suspend fun pollForToken(
        clientId: String,
        code: GitHubDeviceCode,
    ): String {
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
            if (accessToken.isNotBlank()) return accessToken

            when (val error = json.optString("error")) {
                "authorization_pending" -> Unit
                "slow_down" -> intervalMs += 5_000L
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

    private fun validateOwnerSession(accessToken: String): OwnerAccessSession {
        val user = JSONObject(githubGet("$apiBase/user", accessToken))
        val userId = user.optLong("id", -1L)
        if (userId != SourceLabAccessPolicy.ownerGithubUserId) {
            throw GitHubOwnerAuthenticationException("OWNER_ID_MISMATCH")
        }

        val repository = JSONObject(
            githubGet("$apiBase/repos/${SourceLabAccessPolicy.repository}", accessToken),
        )
        if (repository.optLong("id", -1L) != SourceLabAccessPolicy.repositoryId) {
            throw GitHubOwnerAuthenticationException("REPOSITORY_ID_MISMATCH")
        }
        val permissions = repository.optJSONObject("permissions")
        if (permissions?.optBoolean("admin", false) != true) {
            throw GitHubOwnerAuthenticationException("INSUFFICIENT_REPOSITORY_PERMISSION")
        }

        val installations = JSONObject(githubGet("$apiBase/user/installations?per_page=100", accessToken))
            .optJSONArray("installations")
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

        val installedRepositories = JSONObject(
            githubGet(
                "$apiBase/user/installations/${SourceLabAccessPolicy.installationId}/repositories?per_page=100",
                accessToken,
            ),
        ).optJSONArray("repositories")
            ?: throw GitHubOwnerAuthenticationException("INSTALLATION_REPOSITORY_LIST_MISSING")
        val exactRepositoryInstalled = (0 until installedRepositories.length()).any { index ->
            installedRepositories.optJSONObject(index)?.optLong("id", -1L) == SourceLabAccessPolicy.repositoryId
        }
        if (!exactRepositoryInstalled) {
            throw GitHubOwnerAuthenticationException("REPOSITORY_NOT_IN_INSTALLATION")
        }

        return OwnerAccessSession(
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
