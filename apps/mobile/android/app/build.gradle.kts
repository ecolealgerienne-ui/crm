plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.echango.call_tracker"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        applicationId = "com.echango.call_tracker"
        // 24 et non le défaut Flutter : EncryptedSharedPreferences
        // (androidx.security-crypto), qui protège le jeton de l'appareil,
        // demande l'API 23 au minimum, et l'API 24 évite les particularités du
        // Keystore d'Android 6. Android 7 date de 2016 — aucun téléphone
        // commercial en service n'est en dessous.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: signature de production a mettre en place avant toute
            // distribution reelle (APK signe ou Managed Google Play).
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    // Envoi differe, avec reprise et contrainte reseau. C'est le seul
    // ordonnanceur qui survive a la fermeture de l'application et au
    // redemarrage du telephone — un simple thread lance depuis le
    // BroadcastReceiver serait tue avec le processus.
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Chiffrement du jeton au repos. Repli explicite sur des
    // SharedPreferences ordinaires si le Keystore de l'appareil est
    // defaillant — voir SecureSettings.kt.
    implementation("androidx.security:security-crypto:1.0.0")

    // Pas de Room : une seule table, et l'annotation processor (KSP/kapt)
    // ajouterait une etape de generation au build pour un DAO de six colonnes.
    // SQLiteOpenHelper fait le meme travail sans rien generer.
    //
    // Pas d'OkHttp non plus : HttpURLConnection et org.json sont dans le
    // framework Android et suffisent pour un POST JSON.
}

flutter {
    source = "../.."
}
