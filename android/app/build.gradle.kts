import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
}

val localProperties = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) load(f.inputStream())
}

val keystorePath: String? = System.getenv("KEYSTORE_PATH")

android {
    namespace = "com.magpie"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.magpie"
        minSdk = 26
        targetSdk = 35
        // CI passes VERSION_CODE (epoch minutes on release — see release.yml, Phase 8) so each
        // signed release installs cleanly over the previous one; defaults to 1 for local/debug.
        versionCode = System.getenv("VERSION_CODE")?.toIntOrNull() ?: 1
        versionName = System.getenv("VERSION_NAME") ?: "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // AppAuth's redirect receiver activity binds to this scheme — the custom-scheme half
        // of the com.magpie:/oauth2redirect URI registered as a static client on dragonfly-id.
        manifestPlaceholders["appAuthRedirectScheme"] = "com.magpie"
        // Tailnet-only (CLAUDE.md §2/§8) — the default is the real Tailscale Serve HTTPS URL,
        // not a public hostname. Override via local.properties `server.url` for an emulator
        // pointed at a dev instance.
        buildConfigField(
            "String", "SERVER_URL",
            "\"${localProperties.getProperty("server.url", "https://dragonfly.tail2ce561.ts.net/")}\""
        )
    }

    signingConfigs {
        // A stable, committed key so every build — debug, local release, CI release — shares one
        // signing identity. New APKs install over the top of existing ones without Android
        // complaining about INSTALL_FAILED_UPDATE_INCOMPATIBLE. Password is not secret.
        create("stable") {
            storeFile = file("magpie-debug.keystore")
            storePassword = "magpie01"
            keyAlias = "magpie"
            keyPassword = "magpie01"
        }
        // CI's real suite release key, only when KEYSTORE_PATH is supplied in the environment.
        if (keystorePath != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("stable")
        }
        release {
            // Prefer CI's release key; fall back to the stable committed key for local releases.
            signingConfig = signingConfigs.findByName("release")
                ?: signingConfigs.getByName("stable")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.isIncludeAndroidResources = true
    }
}

tasks.withType<Test>().configureEach {
    listOf(
        "roborazzi.test.record",
        "roborazzi.test.verify",
        "roborazzi.test.compare",
    ).forEach { key ->
        (project.findProperty(key) as String?)?.let { systemProperty(key, it) }
    }
    // The Robolectric NATIVE-graphics screenshot tests download a large android-all runtime at
    // test time, which can stall CI. Pass -PexcludeScreenshots to skip them (the gating
    // "Android — Unit Tests" job does this); they still run in the dedicated screenshots job.
    if (project.hasProperty("excludeScreenshots")) {
        filter { excludeTestsMatching("com.magpie.screenshot.*") }
    }
}

dependencies {
    // Hilt 2.60's generated components reference errorprone annotations at compile time; not
    // pulled transitively under AGP 9 / KSP2, so declare it explicitly (compile-only is enough).
    compileOnly("com.google.errorprone:error_prone_annotations:2.50.0")
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)

    // PULSE design system (theme tokens + component kit), from the sibling Pulse repo via the
    // composite build declared in settings.gradle.kts. Magpie leads PulseAccent.Teal.
    implementation(libs.pulse.ui)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    implementation(libs.retrofit)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit.kotlinx.serialization)

    implementation(libs.datastore.preferences)
    implementation(libs.security.crypto)

    // Suite SSO: OpenID Connect authorization-code + PKCE via AppAuth (CLAUDE.md §2, §8 —
    // the BROKER 2e pilot: this is Magpie's ONLY auth path, no password fallback).
    implementation(libs.appauth)

    // Room: the offline cash-entry queue only (CLAUDE.md — the ONE entry surface that's
    // offline; everything else is online-first against the tailnet).
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    testImplementation(libs.mockito.kotlin)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(kotlin("test"))

    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.roborazzi.rule)

    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    debugImplementation(libs.androidx.ui.tooling)
}
