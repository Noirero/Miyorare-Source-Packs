package androidx.preference

/**
 * Test-only ABI shim for ConfigurableSource.
 *
 * The pinned extension is compiled against AndroidX Preference in production, while the
 * deterministic JVM unit-test classpath does not expose PreferenceScreen. Compatibility
 * Farm only needs the type descriptor; preference UI is deliberately not exercised here.
 */
@Suppress("unused")
open class PreferenceScreen
