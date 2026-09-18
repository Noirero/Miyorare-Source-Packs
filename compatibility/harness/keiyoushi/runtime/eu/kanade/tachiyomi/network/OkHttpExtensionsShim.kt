@file:JvmName("OkHttpExtensionsKt")

package eu.kanade.tachiyomi.network

import okhttp3.Call
import okhttp3.Response

/**
 * Test-only host ABI shim for Keiyoushi's suspend OkHttp helpers.
 *
 * Deterministic fixtures remain available when explicitly installed, while
 * real-parser onboarding uses live network traffic by default. These functions
 * reproduce the host method signatures expected by pinned Keiyoushi bytecode.
 */
suspend fun Call.await(): Response = execute()

suspend fun Call.awaitSuccess(): Response {
    val response = execute()
    if (!response.isSuccessful) {
        val code = response.code
        val message = response.message
        response.close()
        error("HTTP $code $message")
    }
    return response
}
