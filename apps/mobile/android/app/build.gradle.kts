import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Secrets de signature, lus dans android/key.properties — un fichier hors du
// depot (voir .gitignore). Absent, le build de release retombe sur la cle de
// DEBOGAGE et le dit bruyamment.
//
// Pourquoi un fichier plutot que des valeurs dans ce build.gradle : ce fichier
// est versionne, les mots de passe non. Et pourquoi un repli plutot qu'un
// echec : un poste de developpement, une CI ou un `flutter test` n'ont aucune
// raison de detenir la cle de production, et un `assembleRelease` qui echoue
// chez tout le monde sauf une personne finit par etre contourne.
val fichierSignature = rootProject.file("key.properties")
val signature = Properties().apply {
    if (fichierSignature.exists()) fichierSignature.inputStream().use { load(it) }
}
val signatureDisponible = signature.getProperty("storeFile") != null

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

    signingConfigs {
        if (signatureDisponible) {
            create("release") {
                storeFile = rootProject.file(signature.getProperty("storeFile"))
                storePassword = signature.getProperty("storePassword")
                keyAlias = signature.getProperty("keyAlias")
                keyPassword = signature.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (signatureDisponible) {
                signingConfigs.getByName("release")
            } else {
                // ⚠️ Repli sur la cle de DEBOGAGE, et il faut qu'il s'entende.
                //
                // Un APK signe en debogage s'installe et fonctionne : rien ne
                // le distingue a l'usage. Mais il ne se met pas a jour
                // par-dessus un APK de production, il ne passe pas Managed
                // Google Play, et sa cle est publique — n'importe qui peut
                // signer une contrefacon que le telephone acceptera comme une
                // mise a jour.
                //
                // C'est exactement le genre de defaut qu'on decouvre le jour
                // de la distribution. D'ou l'avertissement, plutot qu'un
                // commentaire que personne ne lit.
                logger.warn(
                    "\n" +
                    "  ============================================================\n" +
                    "   Call Tracker : APK de RELEASE signe avec la cle de DEBOGAGE\n" +
                    "   android/key.properties est absent.\n" +
                    "   Cet APK ne doit pas etre distribue.\n" +
                    "   Voir apps/mobile/README.md, section Signature.\n" +
                    "  ============================================================\n"
                )
                signingConfigs.getByName("debug")
            }

            // Pas de minification (R8) pour l'instant, et c'est un choix :
            // WorkManager et les receveurs declares au manifeste sont resolus
            // par NOM de classe. R8 est capable de les conserver via les
            // regles fournies par les bibliotheques, mais une erreur y est
            // silencieuse — la capture cesserait simplement de fonctionner sur
            // les appareils de production, sans plantage ni journal.
            // A activer separement, avec un essai sur un vrai telephone.
            isMinifyEnabled = false
            isShrinkResources = false
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
