plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "dev.umer.sgmbot"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.umer.sgmbot"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        ndk { abiFilters += listOf("arm64-v8a") } // the tablet; keeps the APK small
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
