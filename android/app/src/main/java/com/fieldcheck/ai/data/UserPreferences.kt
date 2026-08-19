package com.fieldcheck.ai.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "fieldcheck_prefs")

data class UserSession(val name: String, val email: String)

/**
 * Persists the inspector's name/email locally — "login" here is simple
 * identification only, no password, no server-side session, matching the
 * web dashboard's inspector_name/inspector_email fields — plus the
 * configurable backend base URL, since "localhost" only resolves on the
 * phone itself, never on the developer's machine.
 */
class UserPreferences(private val context: Context) {

    private object Keys {
        val NAME = stringPreferencesKey("inspector_name")
        val EMAIL = stringPreferencesKey("inspector_email")
        val BASE_URL = stringPreferencesKey("api_base_url")
    }

    val session: Flow<UserSession?> = context.dataStore.data.map { prefs ->
        val name = prefs[Keys.NAME]
        val email = prefs[Keys.EMAIL]
        if (!name.isNullOrBlank() && !email.isNullOrBlank()) UserSession(name, email) else null
    }

    val baseUrl: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[Keys.BASE_URL]?.takeIf { it.isNotBlank() } ?: DEFAULT_BASE_URL
    }

    suspend fun currentBaseUrl(): String = baseUrl.first()

    suspend fun saveSession(name: String, email: String) {
        context.dataStore.edit { prefs ->
            prefs[Keys.NAME] = name.trim()
            prefs[Keys.EMAIL] = email.trim()
        }
    }

    suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(Keys.NAME)
            prefs.remove(Keys.EMAIL)
        }
    }

    suspend fun saveBaseUrl(url: String) {
        context.dataStore.edit { prefs ->
            prefs[Keys.BASE_URL] = url.trim().trimEnd('/')
        }
    }

    companion object {
        // 10.0.2.2 is the Android emulator's fixed alias for the host
        // machine's localhost — a real phone must use the host's LAN IP
        // instead (set via the Settings screen).
        const val DEFAULT_BASE_URL = "http://10.0.2.2:8000"
    }
}
