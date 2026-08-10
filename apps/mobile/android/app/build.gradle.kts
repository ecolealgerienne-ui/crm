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

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}

val preparerRobolectric by tasks.registering(Copy::class) {
    from(robolectricRuntime)
    into(layout.buildDirectory.dir("robolectric-runtime"))
}

tasks.withType<Test>().configureEach {
    dependsOn(preparerRobolectric)
    systemProperty("robolectric.offline", "true")
    systemProperty(
        "robolectric.dependency.dir",
        layout.buildDirectory.dir("robolectric-runtime").get().asFile.absolutePath,
    )
}

/**
 * Runtime Android de Robolectric, fourni hors ligne.
 *
 * Robolectric telecharge normalement lui-meme le jar `android-all` au premier
 * test, avec son propre client HTTP. Derriere un proxy TLS d'entreprise, ce
 * client echoue sur la chaine de certificats alors que Gradle, lui, passe :
 * les 29 tests tombaient sur `SSLHandshakeException`, ce qui ressemble a un
 * bogue de code et n'en est pas un. On laisse donc Gradle resoudre le jar, et
 * on met Robolectric hors ligne (voir `tasks.withType<Test>` plus bas).
 *
 * Effet de bord souhaitable : en CI, le runtime est mis en cache avec les
 * autres dependances au lieu d'etre retelecharge a chaque execution.
 */
val robolectricRuntime: Configuration by configurations.creating

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

    // Tests unitaires sur la JVM. Robolectric fournit un vrai SQLite et de
    // vraies SharedPreferences sans appareil ni emulateur : c'est ce qui rend
    // testable la moitie du systeme qui echoue en SILENCE — le curseur de
    // balayage, la file, la plage horaire. Les quatre defauts les plus couteux
    // de la revue du 2026-08-10 etaient tous ici, et aucun n'etait couvert.
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("androidx.test:core:1.6.1")
    // Runtime Android de Robolectric, recupere par GRADLE et non par le
    // resolveur interne de Robolectric. Voir la configuration
    // `robolectricRuntime` plus bas : sans cela, la premiere execution tente
    // un telechargement qui echoue derriere un proxy TLS, et TOUS les tests
    // tombent sur une erreur de certificat sans rapport avec ce qu'ils
    // verifient.
    //
    // ⚠️ Cette version suit le `targetSdk` de l'application, que Robolectric
    // simule par defaut : `15-…` correspond a l'API 35. Le jour ou Flutter
    // fera monter `targetSdk`, les tests echoueront tous sur
    // « Path is not a file: …android-all-instrumented-<N>-… » — c'est le nom
    // du fichier attendu qu'il faudra reprendre ici, et probablement la
    // version de Robolectric avec.
    robolectricRuntime("org.robolectric:android-all-instrumented:15-robolectric-12650502-i7")
    // Le balayage planifie du travail : sans WorkManager initialise, le test
    // echouerait sur l'ordonnanceur au lieu de mesurer le curseur.
    testImplementation("androidx.work:work-testing:2.9.1")
}

flutter {
    source = "../.."
}
