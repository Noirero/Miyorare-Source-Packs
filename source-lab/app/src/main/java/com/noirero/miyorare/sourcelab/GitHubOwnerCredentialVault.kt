package com.noirero.miyorare.sourcelab

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the GitHub user/refresh token pair encrypted with a device-bound
 * Android Keystore key. Nothing is written in plaintext and the key itself is
 * non-exportable. Uninstalling the app removes the app data and invalidates the
 * local sign-in state.
 */
internal object GitHubOwnerCredentialVault {
    private const val keyAlias = "miyorare_source_lab_owner_credential_v1"
    private const val preferencesName = "source_lab_owner_secure_state"
    private const val payloadKey = "github_owner_credential_v1"
    private val aad = "miyorare-source-lab-owner-credential-v1".toByteArray(StandardCharsets.UTF_8)

    fun save(context: Context, credential: GitHubOwnerCredential) {
        val plaintext = JSONObject()
            .put("v", 1)
            .put("accessToken", credential.accessToken)
            .put("accessTokenExpiresAt", credential.accessTokenExpiresAtEpochSeconds ?: JSONObject.NULL)
            .put("refreshToken", credential.refreshToken ?: JSONObject.NULL)
            .put("refreshTokenExpiresAt", credential.refreshTokenExpiresAtEpochSeconds ?: JSONObject.NULL)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        cipher.updateAAD(aad)
        val ciphertext = cipher.doFinal(plaintext)

        val envelope = JSONObject()
            .put("v", 1)
            .put("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .put("ciphertext", Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            .toString()

        preferences(context).edit().putString(payloadKey, envelope).apply()
    }

    fun load(context: Context): GitHubOwnerCredential? {
        val envelopeText = preferences(context).getString(payloadKey, null) ?: return null
        return try {
            val envelope = JSONObject(envelopeText)
            if (envelope.optInt("v", -1) != 1) return clearAndReturnNull(context)

            val iv = Base64.decode(envelope.getString("iv"), Base64.NO_WRAP)
            val ciphertext = Base64.decode(envelope.getString("ciphertext"), Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
            cipher.updateAAD(aad)
            val plaintext = cipher.doFinal(ciphertext)
            val json = JSONObject(String(plaintext, StandardCharsets.UTF_8))
            if (json.optInt("v", -1) != 1) return clearAndReturnNull(context)

            val accessToken = json.optString("accessToken").trim()
            if (accessToken.isBlank()) return clearAndReturnNull(context)

            GitHubOwnerCredential(
                accessToken = accessToken,
                accessTokenExpiresAtEpochSeconds = json.optNullableLong("accessTokenExpiresAt"),
                refreshToken = json.optNullableString("refreshToken"),
                refreshTokenExpiresAtEpochSeconds = json.optNullableLong("refreshTokenExpiresAt"),
            )
        } catch (_: Throwable) {
            clearAndReturnNull(context)
        }
    }

    fun clear(context: Context) {
        preferences(context).edit().remove(payloadKey).apply()
    }

    private fun clearAndReturnNull(context: Context): GitHubOwnerCredential? {
        clear(context)
        return null
    }

    private fun preferences(context: Context) =
        context.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }

        val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return keyGenerator.generateKey()
    }

    private fun JSONObject.optNullableLong(name: String): Long? {
        if (!has(name) || isNull(name)) return null
        return optLong(name, 0L).takeIf { it > 0L }
    }

    private fun JSONObject.optNullableString(name: String): String? {
        if (!has(name) || isNull(name)) return null
        return optString(name).trim().takeIf { it.isNotEmpty() }
    }
}
