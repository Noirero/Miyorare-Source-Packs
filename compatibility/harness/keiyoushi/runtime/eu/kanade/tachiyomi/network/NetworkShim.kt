@file:JvmName("RequestsKt")

package eu.kanade.tachiyomi.network

import okhttp3.CacheControl
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody

/** Deterministic test-only network hook used by real Keiyoushi parser harnesses. */
object DeterministicNetwork {
    data class FixtureResponse(
        val body: String,
        val contentType: String = "text/html; charset=utf-8",
        val code: Int = 200,
    )

    @Volatile
    private var responder: ((Request) -> FixtureResponse)? = null

    fun install(block: (Request) -> FixtureResponse) {
        check(responder == null) { "Deterministic network responder already installed" }
        responder = block
    }

    fun clear() {
        responder = null
    }

    internal fun respond(request: Request): FixtureResponse =
        responder?.invoke(request) ?: error("Unexpected live-network attempt: ${request.method} ${request.url}")
}

private class UncaughtExceptionInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response = chain.proceed(chain.request())
}

private class UserAgentInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response = chain.proceed(chain.request())
}

private class CloudflareInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response = chain.proceed(chain.request())
}

private class DeterministicFixtureInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val fixture = DeterministicNetwork.respond(request)
        return Response.Builder()
            .request(request)
            .protocol(Protocol.HTTP_1_1)
            .code(fixture.code)
            .message(if (fixture.code in 200..299) "OK" else "Fixture")
            .body(fixture.body.toResponseBody(fixture.contentType.toMediaType()))
            .build()
    }
}

class NetworkHelper {
    val client: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(UncaughtExceptionInterceptor())
        .addInterceptor(UserAgentInterceptor())
        .addInterceptor(CloudflareInterceptor())
        .addInterceptor(DeterministicFixtureInterceptor())
        .build()
}

private val DEFAULT_CACHE_CONTROL: CacheControl = CacheControl.Builder().build()
private val DEFAULT_HEADERS: Headers = Headers.Builder().build()
private val DEFAULT_BODY: RequestBody = ByteArray(0).toRequestBody(null)

fun GET(
    url: String,
    headers: Headers = DEFAULT_HEADERS,
    cache: CacheControl = DEFAULT_CACHE_CONTROL,
): Request = Request.Builder()
    .url(url)
    .headers(headers)
    .cacheControl(cache)
    .get()
    .build()

fun GET(
    url: HttpUrl,
    headers: Headers = DEFAULT_HEADERS,
    cache: CacheControl = DEFAULT_CACHE_CONTROL,
): Request = Request.Builder()
    .url(url)
    .headers(headers)
    .cacheControl(cache)
    .get()
    .build()

fun POST(
    url: String,
    headers: Headers = DEFAULT_HEADERS,
    body: RequestBody = DEFAULT_BODY,
    cache: CacheControl = DEFAULT_CACHE_CONTROL,
): Request = Request.Builder()
    .url(url)
    .headers(headers)
    .cacheControl(cache)
    .post(body)
    .build()
