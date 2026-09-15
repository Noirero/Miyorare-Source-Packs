package com.noirero.miyorare.sourcelab

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

internal object GitHubAppPublicConfig {
    const val clientId: String = "Iv23lijwK22xASXNEBkP"
    const val appId: Long = 4959004L
    const val installationId: Long = 162045953L
    const val ownerGithubUserId: Long = 149634319L
    const val repository: String = "Noirero/Miyorare-Source-Packs"
}

internal data class DeviceAuthorization(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val expiresInSeconds: Long,
    val intervalSeconds: Long,
)

internal data class GitHubIdentity(
    val id: Long,
    val login: String,
)

internal sealed interface DeviceTokenPoll {
    data class Success(val accessToken: String) : DeviceTokenPoll
    data object Pending : DeviceTokenPoll
    data class SlowDown(val extraDelaySeconds: Long = 5) : DeviceTokenPoll
    data object Expired : DeviceTokenPoll
    data object Denied : DeviceTokenPoll
    data class Failed(val message: String) : DeviceTokenPoll
}

internal object GitHubDeviceFlowClient {
    private const val deviceCodeUrl = "https://github.com/login/device/code"
    private const val tokenUrl = "https://github.com/login/oauth/access_token"
    private const val userUrl = "https://api.github.com/user"

    fun requestAuthorization(): DeviceAuthorization {
        val response = postForm(
            deviceCodeUrl,
            mapOf(
                "client_id" to GitHubAppPublicConfig.clientId,
                "scope" to "read:user",
            ),
        )
        val json = JSONObject(response)
        return DeviceAuthorization(
            deviceCode = json.getString("device_code"),
            userCode = json.getString("user_code"),
            verificationUri = json.getString("verification_uri"),
            expiresInSeconds = json.getLong("expires_in"),
            intervalSeconds = json.optLong("interval", 5L).coerceAtLeast(5L),
        )
    }

    fun pollToken(deviceCode: String): DeviceTokenPoll {
        val response = postForm(
            tokenUrl,
            mapOf(
                "client_id" to GitHubAppPublicConfig.clientId,
                "device_code" to deviceCode,
                "grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
            ),
        )
        val json = JSONObject(response)
        json.optString("access_token").takeIf { it.isNotBlank() }?.let {
            return DeviceTokenPoll.Success(it)
        }
        return when (json.optString("error")) {
            "authorization_pending" -> DeviceTokenPoll.Pending
            "slow_down" -> DeviceTokenPoll.SlowDown()
            "expired_token" -> DeviceTokenPoll.Expired
            "access_denied" -> DeviceTokenPoll.Denied
            else -> DeviceTokenPoll.Failed(
                json.optString("error_description").ifBlank {
                    json.optString("error").ifBlank { "UNKNOWN_DEVICE_FLOW_ERROR" }
                },
            )
        }
    }

    fun fetchIdentity(accessToken: String): GitHubIdentity {
        val connection = (URL(userUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $accessToken")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab")
        }
        val code = connection.responseCode
        val body = (if (code in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()
            ?.use { it.readText() }
            .orEmpty()
        if (code !in 200..299) {
            error("GitHub identity request failed: HTTP $code")
        }
        val json = JSONObject(body)
        return GitHubIdentity(
            id = json.getLong("id"),
            login = json.getString("login"),
        )
    }

    private fun postForm(url: String, values: Map<String, String>): String {
        val form = values.entries.joinToString("&") { (key, value) ->
            "${encode(key)}=${encode(value)}"
        }
        val bytes = form.toByteArray(Charsets.UTF_8)
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 15_000
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab")
            setFixedLengthStreamingMode(bytes.size)
        }
        connection.outputStream.use { it.write(bytes) }
        val code = connection.responseCode
        val body = (if (code in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()
            ?.use { it.readText() }
            .orEmpty()
        if (code !in 200..299) {
            error("GitHub Device Flow request failed: HTTP $code")
        }
        return body
    }

    private fun encode(value: String): String = URLEncoder.encode(value, Charsets.UTF_8.name())
}
