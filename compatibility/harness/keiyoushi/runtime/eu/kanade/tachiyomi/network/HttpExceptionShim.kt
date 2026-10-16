package eu.kanade.tachiyomi.network

/**
 * Test-host ABI from keiyoushi/extensions-lib 42255ee5fa, network/HttpException.kt.
 * Madara 1.6 references this host exception while loading its parser class.
 */
class HttpException(val code: Int) : IllegalStateException("HTTP error $code")
