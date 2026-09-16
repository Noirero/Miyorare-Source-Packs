plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val sourceLabGitHubClientId = providers.gradleProperty("SOURCE_LAB_GITHUB_CLIENT_ID")
    .orElse(providers.environmentVariable("SOURCE_LAB_GITHUB_CLIENT_ID"))
    .orElse("")
    .get()
    .trim()
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

val sourceLabVersionCode = providers.environmentVariable("SOURCE_LAB_VERSION_CODE")
    .orNull
    ?.toIntOrNull()
    ?.takeIf { it > 0 }
    ?: 6
val sourceLabVersionName = providers.environmentVariable("SOURCE_LAB_VERSION_NAME")
    .orNull
    ?.trim()
    ?.takeIf { it.isNotEmpty() }
    ?: "0.1.5"

val sourceLabKeystorePath = providers.environmentVariable("SOURCE_LAB_KEYSTORE_PATH").orNull
val sourceLabStorePassword = providers.environmentVariable("SOURCE_LAB_STORE_PASSWORD").orNull
val sourceLabKeyAlias = providers.environmentVariable("SOURCE_LAB_KEY_ALIAS").orNull
val sourceLabKeyPassword = providers.environmentVariable("SOURCE_LAB_KEY_PASSWORD").orNull
val sourceLabStableSigningConfigured = listOf(
    sourceLabKeystorePath,
    sourceLabStorePassword,
    sourceLabKeyAlias,
    sourceLabKeyPassword,
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
        buildConfigField(
            "String",
            "SOURCE_LAB_GITHUB_CLIENT_ID",
            "\"$sourceLabGitHubClientId\"",
        )
    }

    signingConfigs {
        if (sourceLabStableSigningConfigured) {
            create("sourceLabStable") {
                storeFile = file(sourceLabKeystorePath!!)
                storePassword = sourceLabStorePassword
                keyAlias = sourceLabKeyAlias
                keyPassword = sourceLabKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (sourceLabStableSigningConfigured) {
                signingConfig = signingConfigs.getByName("sourceLabStable")
            }
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
        buildConfig = true
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
