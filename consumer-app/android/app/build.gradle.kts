import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing.
//
// The upload key lives outside this repository and is never committed: an APK
// signed with the debug key can be resigned by anyone, and Play will not take
// it. `key.properties` points at the keystore and is gitignored; see
// key.properties.example and consumer-app/README.md.
//
// Without it, a release build fails rather than quietly falling back to the
// debug key. ALLOW_DEBUG_SIGNING=1 opts back in for a throwaway local build.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { load(it) }
    }
}

val allowDebugSigning =
    System.getenv("ALLOW_DEBUG_SIGNING") == "1" ||
        (project.findProperty("allowDebugSigning") as String?) == "true"

fun keystoreProperty(name: String): String =
    keystoreProperties.getProperty(name)
        ?: throw GradleException("$name is missing from ${keystorePropertiesFile.path}")

android {
    namespace = "com.anticounterfeitmed.consumer_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.anticounterfeitmed.consumer_app"
        // Firebase App Check needs 23; the Flutter floor is higher than that
        // already, so take whichever is greater rather than pinning a number
        // that quietly goes stale.
        minSdk = maxOf(flutter.minSdkVersion, 23)
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    if (keystorePropertiesFile.exists()) {
        signingConfigs {
            create("release") {
                val store = file(keystoreProperty("storeFile"))
                if (!store.exists()) {
                    throw GradleException(
                        "keystore not found at ${store.path} (storeFile in ${keystorePropertiesFile.path})",
                    )
                }
                storeFile = store
                storePassword = keystoreProperty("storePassword")
                keyAlias = keystoreProperty("keyAlias")
                keyPassword = keystoreProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = when {
                keystorePropertiesFile.exists() -> signingConfigs.getByName("release")
                // Produces an APK that cannot be distributed. The build is
                // stopped below unless that was asked for explicitly.
                else -> signingConfigs.getByName("debug")
            }
        }
    }
}

// Stop at execution time, not configuration time, so that debug builds and
// tooling that merely configures the project are unaffected.
if (!keystorePropertiesFile.exists() && !allowDebugSigning) {
    gradle.taskGraph.whenReady {
        if (allTasks.none { it.name.contains("Release") }) return@whenReady
        throw GradleException(
            """
            No release keystore, so this build would be signed with the debug key.

            A debug-signed APK can be resigned by anyone and Play will not accept
            it. Create an upload key and keep it outside the repository:

              keytool -genkey -v -keystore ~/keys/anticounterfeitmed-upload.jks \
                -keyalg RSA -keysize 4096 -validity 10000 -alias upload

            Then write consumer-app/android/key.properties from
            key.properties.example. Back the keystore up: losing it means the app
            can never be updated under the same identity again.

            For a throwaway local build, and nothing else:
              ALLOW_DEBUG_SIGNING=1 flutter build apk --release
            """.trimIndent(),
        )
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
