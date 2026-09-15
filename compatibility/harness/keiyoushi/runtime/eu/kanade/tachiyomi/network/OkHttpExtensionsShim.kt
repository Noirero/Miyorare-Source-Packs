@file:JvmName("OkHttpExtensionsKt")

package eu.kanade.tachiyomi.network

import okhttp3.Call
import okhttp3.Response

/**
 * Test-only host ABI shim for Keiyoushi's suspend OkHttp helpers.
 *
 * Real network traffic is still blocked by DeterministicNetwork's interceptor.
 * These functions only reproduce the host method signatures expected by pinned
 * Keiyoushi bytecode so real source parser code can execute in JVM CI.
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
