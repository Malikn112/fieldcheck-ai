# Add project specific ProGuard rules here.
# Debug builds don't run ProGuard/R8 minification (see build.gradle.kts).
# If you enable minification for release builds, keep the network model
# classes so Gson's reflection-based (de)serialization keeps working:
-keep class com.fieldcheck.ai.network.** { *; }
