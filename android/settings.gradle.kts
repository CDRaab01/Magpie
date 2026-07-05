pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "Magpie"
include(":app")

// PULSE design system, consumed as a composite build of the sibling Pulse repo
// (<parent>/{Magpie,Pulse}); Gradle substitutes the design.pulse:pulse-ui dependency with the
// included build. Required — the app's whole theme lives there — so there is no exists() gate:
// a missing checkout should fail loudly. CI checks the Pulse repo out next to this one (see
// .github/workflows/ci.yml).
includeBuild("../../Pulse")
