package com.noirero.miyorare.sourcelab

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.RSAPublicKeySpec
import java.util.Base64
import java.security.SecureRandom
import java.util.zip.ZipInputStream

internal data class BackendAuthorizationProof(
    val authorized: Boolean,
    val reason: String,
    val challenge: String? = null,
    val runId: Long? = null,
    val expiresAtEpochSeconds: Long? = null,
) {
    fun applyTo(session: OwnerAccessSession): OwnerAccessSession {
        if (!authorized || expiresAtEpochSeconds == null) return session
        return session.copy(
            backendAuthorized = true,
            backendAuthorizationExpiresAtEpochSeconds = expiresAtEpochSeconds,
            // P0 backend authorization proves the owner session only. Individual
            // write capabilities remain fail-closed until their own control paths
            // are wired and bound to exact candidate evidence.
            backendCapabilities = emptySet(),
        )
    }
}

/**
 * Establishes a short-lived backend-authorized owner session without embedding a
 * write credential or a private signing key in the APK.
 *
 * The Android app dispatches a dedicated workflow on the repository default
 * branch with a fresh 256-bit challenge. The workflow is allowed to mint a
 * GitHub Actions OIDC token only after it verifies the immutable owner id,
 * repository and event. The app then verifies that GitHub-signed JWT against
 * GitHub's OIDC JWKS and exact immutable claims before accepting the session.
 */
internal object SourceLabBackendAuthorization {
    private const val repository = SourceLabAccessPolicy.repository
    private const val apiBase = "https://api.github.com/repos/$repository"
    private const val workflowFile = "source-lab-backend-authorization.yml"
    private const val workflowName = "Source Lab Backend Authorization"
    private const val mainRef = "main"
    private const val oidcIssuer = "https://token.actions.githubusercontent.com"
    private const val oidcConfiguration =
        "$oidcIssuer/.well-known/openid-configuration"
    private const val pollIntervalMs = 2_000L
    private const val maxPolls = 45

    suspend fun authorize(githubAccessToken: String): BackendAuthorizationProof =
        withContext(Dispatchers.IO) {
            if (githubAccessToken.isBlank()) {
                return@withContext BackendAuthorizationProof(
                    authorized = false,
                    reason = "GITHUB_ACCESS_TOKEN_REQUIRED",
                )
            }

            val challenge = generateChallenge()
            try {
                dispatchAuthorization(githubAccessToken, challenge)
                val run = waitForAuthorizationRun(githubAccessToken, challenge)
                    ?: return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = "BACKEND_AUTHORIZATION_TIMEOUT",
                        challenge = challenge,
                    )

                if (run.conclusion != "success") {
                    return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = "BACKEND_AUTHORIZATION_DENIED",
                        challenge = challenge,
                        runId = run.id,
                    )
                }

                val artifact = waitForAuthorizationArtifact(githubAccessToken, run.id, challenge)
                    ?: return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = "BACKEND_AUTHORIZATION_PROOF_MISSING",
                        challenge = challenge,
                        runId = run.id,
                    )

                val archive = downloadArtifact(githubAccessToken, artifact.downloadUrl)
                val proofFiles = unzipProof(archive)
                val jwt = proofFiles["authorization.jwt"]?.toString(StandardCharsets.UTF_8)?.trim()
                    ?.takeIf { it.isNotBlank() }
                    ?: return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = "BACKEND_AUTHORIZATION_JWT_MISSING",
                        challenge = challenge,
                        runId = run.id,
                    )
                val metadataText = proofFiles["metadata.json"]?.toString(StandardCharsets.UTF_8)
                    ?: return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = "BACKEND_AUTHORIZATION_METADATA_MISSING",
                        challenge = challenge,
                        runId = run.id,
                    )
                val metadata = JSONObject(metadataText)
                val metadataFailure = validateMetadata(metadata, challenge, run.id)
                if (metadataFailure != null) {
                    return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = metadataFailure,
                        challenge = challenge,
                        runId = run.id,
                    )
                }

                val verified = verifyGithubOidcJwt(jwt, challenge, run.id)
                if (!verified.authorized) {
                    return@withContext BackendAuthorizationProof(
                        authorized = false,
                        reason = verified.reason,
                        challenge = challenge,
                        runId = run.id,
                    )
                }

                BackendAuthorizationProof(
                    authorized = true,
                    reason = "BACKEND_AUTHORIZED",
                    challenge = challenge,
                    runId = run.id,
                    expiresAtEpochSeconds = verified.expiresAtEpochSeconds,
                )
            } catch (error: BackendAuthorizationHttpException) {
                BackendAuthorizationProof(
                    authorized = false,
                    reason = when (error.statusCode) {
                        404 -> "BACKEND_AUTHORIZATION_WORKFLOW_NOT_INSTALLED"
                        401, 403 -> "BACKEND_AUTHORIZATION_GITHUB_PERMISSION_DENIED"
                        else -> "BACKEND_AUTHORIZATION_HTTP_${error.statusCode}"
                    },
                    challenge = challenge,
                )
            } catch (_: Throwable) {
                BackendAuthorizationProof(
                    authorized = false,
                    reason = "BACKEND_AUTHORIZATION_NETWORK_OR_PROOF_ERROR",
                    challenge = challenge,
                )
            }
        }

    private fun dispatchAuthorization(token: String, challenge: String) {
        val body = JSONObject()
            .put("ref", mainRef)
            .put("inputs", JSONObject().put("challenge", challenge))
            .toString()
        githubRequest(
            url = "$apiBase/actions/workflows/$workflowFile/dispatches",
            token = token,
            method = "POST",
            body = body,
            expected = setOf(204),
        )
    }

    private suspend fun waitForAuthorizationRun(
        token: String,
        challenge: String,
    ): AuthorizationRun? {
        val expectedTitle = "Source Lab auth $challenge"
        repeat(maxPolls) {
            val payload = JSONObject(
                githubRequest(
                    url = "$apiBase/actions/workflows/$workflowFile/runs" +
                        "?event=workflow_dispatch&branch=$mainRef&per_page=20",
                    token = token,
                ).body,
            )
            val runs = payload.getJSONArray("workflow_runs")
            for (index in 0 until runs.length()) {
                val run = runs.getJSONObject(index)
                if (run.optString("display_title") != expectedTitle) continue
                val actorId = run.optJSONObject("actor")?.optLong("id", -1L) ?: -1L
                if (actorId != SourceLabAccessPolicy.ownerGithubUserId) continue
                val status = run.optString("status")
                if (status == "completed") {
                    return AuthorizationRun(
                        id = run.getLong("id"),
                        conclusion = run.optString("conclusion"),
                    )
                }
            }
            delay(pollIntervalMs)
        }
        return null
    }

    private suspend fun waitForAuthorizationArtifact(
        token: String,
        runId: Long,
        challenge: String,
    ): AuthorizationArtifact? {
        val expectedName = "source-lab-authorization-$challenge"
        repeat(10) {
            val payload = JSONObject(
                githubRequest(
                    url = "$apiBase/actions/runs/$runId/artifacts?per_page=20",
                    token = token,
                ).body,
            )
            val artifacts = payload.getJSONArray("artifacts")
            for (index in 0 until artifacts.length()) {
                val artifact = artifacts.getJSONObject(index)
                if (artifact.optString("name") != expectedName) continue
                if (artifact.optBoolean("expired", false)) return null
                return AuthorizationArtifact(
                    downloadUrl = artifact.getString("archive_download_url"),
                )
            }
            delay(1_000L)
        }
        return null
    }

    private fun downloadArtifact(token: String, apiUrl: String): ByteArray {
        val first = openConnection(apiUrl, token).apply {
            requestMethod = "GET"
            instanceFollowRedirects = false
        }
        try {
            val code = first.responseCode
            if (code !in 300..399) {
                if (code !in 200..299) throw BackendAuthorizationHttpException(code)
                return first.inputStream.use { it.readBytesLimited(1_048_576) }
            }
            val location = first.getHeaderField("Location")
                ?: error("Artifact redirect missing Location")
            val second = (URL(location).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 10_000
                readTimeout = 15_000
                instanceFollowRedirects = true
                useCaches = false
            }
            return try {
                val secondCode = second.responseCode
                if (secondCode !in 200..299) throw BackendAuthorizationHttpException(secondCode)
                second.inputStream.use { it.readBytesLimited(1_048_576) }
            } finally {
                second.disconnect()
            }
        } finally {
            first.disconnect()
        }
    }

    private fun unzipProof(archive: ByteArray): Map<String, ByteArray> {
        val result = mutableMapOf<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(archive)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (!entry.isDirectory) {
                    val safeName = entry.name.substringAfterLast('/')
                    if (safeName == "authorization.jwt" || safeName == "metadata.json") {
                        result[safeName] = zip.readBytesLimited(256 * 1024)
                    }
                }
                zip.closeEntry()
            }
        }
        return result
    }

    private fun validateMetadata(
        metadata: JSONObject,
        challenge: String,
        runId: Long,
    ): String? {
        if (metadata.optInt("schemaVersion", -1) != 1) return "BACKEND_METADATA_SCHEMA_MISMATCH"
        if (metadata.optString("challenge") != challenge) return "BACKEND_CHALLENGE_MISMATCH"
        if (metadata.optString("repository") != repository) return "BACKEND_REPOSITORY_MISMATCH"
        if (metadata.optString("actorId") != SourceLabAccessPolicy.ownerGithubUserId.toString()) {
            return "BACKEND_ACTOR_MISMATCH"
        }
        if (metadata.optString("runId") != runId.toString()) return "BACKEND_RUN_MISMATCH"
        if (metadata.optString("ref") != "refs/heads/main") return "BACKEND_REF_MISMATCH"
        if (metadata.optString("event") != "workflow_dispatch") return "BACKEND_EVENT_MISMATCH"
        return null
    }

    private fun verifyGithubOidcJwt(
        jwt: String,
        challenge: String,
        runId: Long,
    ): JwtVerificationResult {
        val parts = jwt.split('.')
        if (parts.size != 3) return JwtVerificationResult(false, "BACKEND_JWT_MALFORMED")

        val header = JSONObject(String(base64UrlDecode(parts[0]), StandardCharsets.UTF_8))
        if (header.optString("alg") != "RS256") {
            return JwtVerificationResult(false, "BACKEND_JWT_ALGORITHM_REJECTED")
        }
        val kid = header.optString("kid").takeIf { it.isNotBlank() }
            ?: return JwtVerificationResult(false, "BACKEND_JWT_KID_MISSING")

        val configuration = JSONObject(publicRequest(oidcConfiguration))
        if (configuration.optString("issuer") != oidcIssuer) {
            return JwtVerificationResult(false, "BACKEND_OIDC_ISSUER_DISCOVERY_MISMATCH")
        }
        val jwksUri = configuration.optString("jwks_uri").takeIf { it.startsWith("https://") }
            ?: return JwtVerificationResult(false, "BACKEND_OIDC_JWKS_MISSING")
        val jwks = JSONObject(publicRequest(jwksUri)).getJSONArray("keys")
        val jwk = findJwk(jwks, kid)
            ?: return JwtVerificationResult(false, "BACKEND_JWT_SIGNING_KEY_MISSING")

        val modulus = BigInteger(1, base64UrlDecode(jwk.getString("n")))
        val exponent = BigInteger(1, base64UrlDecode(jwk.getString("e")))
        val publicKey = KeyFactory.getInstance("RSA")
            .generatePublic(RSAPublicKeySpec(modulus, exponent))
        val signature = Signature.getInstance("SHA256withRSA")
        signature.initVerify(publicKey)
        signature.update("${parts[0]}.${parts[1]}".toByteArray(StandardCharsets.US_ASCII))
        if (!signature.verify(base64UrlDecode(parts[2]))) {
            return JwtVerificationResult(false, "BACKEND_JWT_SIGNATURE_INVALID")
        }

        val payload = JSONObject(String(base64UrlDecode(parts[1]), StandardCharsets.UTF_8))
        val failure = SourceLabOidcClaimsValidator.validate(
            payload = payload,
            expectedChallenge = challenge,
            expectedRunId = runId,
        )
        if (failure != null) return JwtVerificationResult(false, failure)
        return JwtVerificationResult(
            authorized = true,
            reason = "BACKEND_AUTHORIZED",
            expiresAtEpochSeconds = payload.getLong("exp"),
        )
    }

    private fun findJwk(keys: JSONArray, kid: String): JSONObject? {
        for (index in 0 until keys.length()) {
            val key = keys.getJSONObject(index)
            if (key.optString("kid") == kid && key.optString("kty") == "RSA") return key
        }
        return null
    }

    private fun githubRequest(
        url: String,
        token: String,
        method: String = "GET",
        body: String? = null,
        expected: Set<Int> = (200..299).toSet(),
    ): HttpResult {
        val connection = openConnection(url, token).apply {
            requestMethod = method
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        return try {
            if (body != null) {
                connection.outputStream.use { output ->
                    output.write(body.toByteArray(StandardCharsets.UTF_8))
                }
            }
            val code = connection.responseCode
            if (code !in expected) throw BackendAuthorizationHttpException(code)
            val text = if (code == 204) "" else connection.inputStream.bufferedReader().use { it.readText() }
            HttpResult(code, text)
        } finally {
            connection.disconnect()
        }
    }

    private fun openConnection(url: String, token: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1")
            useCaches = false
        }

    private fun publicRequest(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Miyorare-Source-Lab/0.1")
            useCaches = false
        }
        return try {
            val code = connection.responseCode
            if (code !in 200..299) throw BackendAuthorizationHttpException(code)
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun generateChallenge(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return bytes.joinToString(separator = "") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun base64UrlDecode(value: String): ByteArray = Base64.getUrlDecoder().decode(value)

    private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
        val buffer = ByteArray(8 * 1024)
        val output = java.io.ByteArrayOutputStream()
        var total = 0
        while (true) {
            val read = read(buffer)
            if (read < 0) break
            total += read
            require(total <= limit) { "Backend authorization response exceeded size limit" }
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }

    private data class AuthorizationRun(val id: Long, val conclusion: String)
    private data class AuthorizationArtifact(val downloadUrl: String)
    private data class HttpResult(val statusCode: Int, val body: String)
    private data class JwtVerificationResult(
        val authorized: Boolean,
        val reason: String,
        val expiresAtEpochSeconds: Long? = null,
    )

    private class BackendAuthorizationHttpException(val statusCode: Int) : RuntimeException()
}

internal object SourceLabOidcClaimsValidator {
    private const val issuer = "https://token.actions.githubusercontent.com"
    private const val repository = "Noirero/Miyorare-Source-Packs"
    private const val repositoryId = "1367256631"
    private const val ownerId = "149634319"
    private const val workflowRef =
        "Noirero/Miyorare-Source-Packs/.github/workflows/source-lab-backend-authorization.yml@refs/heads/main"
    private const val idBoundSubject =
        "repo:Noirero@149634319/Miyorare-Source-Packs@1367256631:ref:refs/heads/main"
    private const val legacySubject = "repo:Noirero/Miyorare-Source-Packs:ref:refs/heads/main"

    fun validate(
        payload: JSONObject,
        expectedChallenge: String,
        expectedRunId: Long,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000L,
    ): String? {
        if (payload.optString("iss") != issuer) return "BACKEND_CLAIM_ISSUER_MISMATCH"
        if (!audienceContains(payload.opt("aud"), "miyorare-source-lab:$expectedChallenge")) {
            return "BACKEND_CLAIM_AUDIENCE_MISMATCH"
        }
        if (payload.optString("repository") != repository) return "BACKEND_CLAIM_REPOSITORY_MISMATCH"
        if (payload.optString("repository_id") != repositoryId) return "BACKEND_CLAIM_REPOSITORY_ID_MISMATCH"
        if (payload.optString("repository_owner_id") != ownerId) return "BACKEND_CLAIM_OWNER_ID_MISMATCH"
        if (payload.optString("actor_id") != ownerId) return "BACKEND_CLAIM_ACTOR_ID_MISMATCH"
        if (payload.optString("event_name") != "workflow_dispatch") return "BACKEND_CLAIM_EVENT_MISMATCH"
        if (payload.optString("ref") != "refs/heads/main") return "BACKEND_CLAIM_REF_MISMATCH"
        if (payload.optString("workflow_ref") != workflowRef) return "BACKEND_CLAIM_WORKFLOW_REF_MISMATCH"
        if (payload.optString("workflow") != "Source Lab Backend Authorization") {
            return "BACKEND_CLAIM_WORKFLOW_MISMATCH"
        }
        val subject = payload.optString("sub")
        if (subject != idBoundSubject && subject != legacySubject) {
            return "BACKEND_CLAIM_SUBJECT_MISMATCH"
        }
        if (payload.optString("run_id") != expectedRunId.toString()) return "BACKEND_CLAIM_RUN_ID_MISMATCH"

        val exp = payload.optLong("exp", 0L)
        val nbf = payload.optLong("nbf", 0L)
        val iat = payload.optLong("iat", 0L)
        if (exp <= 0L || exp <= nowEpochSeconds - 30L) return "BACKEND_CLAIM_EXPIRED"
        if (nbf > nowEpochSeconds + 30L) return "BACKEND_CLAIM_NOT_YET_VALID"
        if (iat <= 0L || iat > nowEpochSeconds + 60L || iat < nowEpochSeconds - 600L) {
            return "BACKEND_CLAIM_ISSUED_AT_INVALID"
        }
        return null
    }

    private fun audienceContains(raw: Any?, expected: String): Boolean = when (raw) {
        is String -> raw == expected
        is JSONArray -> (0 until raw.length()).any { raw.optString(it) == expected }
        else -> false
    }
}
