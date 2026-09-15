plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val sourceLabVersionCode = System.getenv("SOURCE_LAB_VERSION_CODE")?.toIntOrNull() ?: 1
val sourceLabVersionName = System.getenv("SOURCE_LAB_VERSION_NAME") ?: "0.1.0"
val updateStorePath = System.getenv("SOURCE_LAB_KEYSTORE_PATH")
val updateStorePassword = System.getenv("SOURCE_LAB_KEYSTORE_PASSWORD")
val updateKeyAlias = System.getenv("SOURCE_LAB_KEY_ALIAS")
val updateKeyPassword = System.getenv("SOURCE_LAB_KEY_PASSWORD")
val hasStableUpdateSigning = listOf(
    updateStorePath,
    updateStorePassword,
    updateKeyAlias,
    updateKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "com.noirero.miyorare.sourcelab"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.noirero.miyorare.sourcelab"
        minSdk = 26
        targetSdk = 35
        versionCode = sourceLabVersionCode
        versionName = sourceLabVersionName
    }

    val stableUpdateSigning = if (hasStableUpdateSigning) {
        signingConfigs.create("sourceLabStableUpdate") {
            storeFile = file(updateStorePath!!)
            storePassword = updateStorePassword
            keyAlias = updateKeyAlias
            keyPassword = updateKeyPassword
        }
    } else {
        null
    }

    buildTypes {
        getByName("debug") {
            stableUpdateSigning?.let { signingConfig = it }
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
