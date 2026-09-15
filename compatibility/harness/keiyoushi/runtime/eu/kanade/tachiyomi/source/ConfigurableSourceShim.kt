package eu.kanade.tachiyomi.source

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import androidx.preference.PreferenceScreen
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.get

/** Test-only Mihon host ABI required by configurable Keiyoushi sources. */
@Suppress("unused")
interface ConfigurableSource {
    fun getSourcePreferences(): SharedPreferences =
        Injekt.get<Application>().getSharedPreferences("compatibility_farm_source", Context.MODE_PRIVATE)

    fun setupPreferenceScreen(screen: PreferenceScreen)
}
