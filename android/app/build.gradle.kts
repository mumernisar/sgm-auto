plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// Version lives in ../VERSION (bumped by ../release.sh): "MAJOR.MINOR.PATCH" or "MAJOR.MINOR.PATCH-beta.N".
// versionCode always grows: a beta counts below its final release (0.1.0-beta.2 < 0.1.0 < 0.1.1-beta.1).
val appVersion = rootProject.file("../VERSION").readText().trim()
val appVersionCode = Regex("""(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?""").matchEntire(appVersion)!!.destructured
    .let { (major, minor, patch, beta) ->
        major.toInt() * 1_000_000 + minor.toInt() * 10_000 + patch.toInt() * 100 + (beta.toIntOrNull() ?: 99)
    }

android {
    namespace = "dev.umer.sgmbot"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.umer.sgmbot"
        minSdk = 30
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersion
        ndk { abiFilters += listOf("arm64-v8a") } // the tablet; keeps the APK small
    }

    buildFeatures {
        aidl = true        // IShellService: the Shizuku shell
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug") // personal sideloaded app
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.10" // Chaquopy's OpenCV wheels exist for 3.10
        pip {
            install("numpy")
            install("opencv-python")
        }
    }
}

dependencies {
    implementation("cz.adaptech.tesseract4android:tesseract4android:4.9.0")
    // without root: a shell with adb's rights through Shizuku (https://shizuku.rikka.app/)
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")
}

// The bot's Python package and templates live in the repo root (shared with the Mac version):
// copy them into the app's source tree before every build. The copies are git-ignored.
val syncBot by tasks.registering(Sync::class) {
    from(rootProject.file("../bot"))
    into(layout.projectDirectory.dir("src/main/python/bot"))
    exclude("__pycache__/**")
}
val syncTemplates by tasks.registering(Sync::class) {
    from(rootProject.file("../templates"))
    into(layout.projectDirectory.dir("src/main/assets/templates"))
    exclude("_sheet.png")
}
tasks.named("preBuild") { dependsOn(syncBot, syncTemplates) }
// Chaquopy's and AGP's merge tasks read those copies, so they must run after them
tasks.configureEach {
    if (name.endsWith("PythonSources") || name.endsWith("Assets")) {
        dependsOn(syncBot, syncTemplates)
    }
}
