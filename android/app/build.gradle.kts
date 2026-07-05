plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
}

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
    }

    signingConfigs {
        // A stable, committed key so every build — debug, local release, CI release — shares one
        // signing identity. New APKs install over the top of existing ones without Android
        // complaining about INSTALL_FAILED_UPDATE_INCOMPATIBLE. Password is not secret.
        // The suite release key (Phase 8) supersedes this for real releases.
        create("stable") {
            storeFile = file("magpie-debug.keystore")
            storePassword = "magpie01"
            keyAlias = "magpie"
            keyPassword = "magpie01"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("stable")
        }
        release {
            signingConfig = signingConfigs.getByName("stable")
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
}

dependencies {
    // Hilt 2.60's generated components reference errorprone annotations at compile time; not
    // pulled transitively under AGP 9 / KSP2, so declare it explicitly (compile-only is enough).
    compileOnly("com.google.errorprone:error_prone_annotations:2.50.0")
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)

    // PULSE design system (theme tokens + component kit), from the sibling Pulse repo via the
    // composite build declared in settings.gradle.kts. Magpie leads PulseAccent.Teal.
    implementation(libs.pulse.ui)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)

    debugImplementation(libs.androidx.ui.tooling)
}
