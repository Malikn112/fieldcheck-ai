package com.fieldcheck.ai.network

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Builds (and caches) a Retrofit client for the currently-configured backend
 * base URL. The base URL is user-configurable at runtime (Settings screen),
 * so this can't be a single static singleton the way it usually would be —
 * it rebuilds only when the URL actually changes.
 */
object NetworkModule {
    private var cachedBaseUrl: String? = null
    private var cachedApi: FieldCheckApi? = null

    fun apiFor(baseUrl: String): FieldCheckApi {
        val normalized = baseUrl.trim().trimEnd('/')
        val existing = cachedApi
        if (existing != null && cachedBaseUrl == normalized) return existing

        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .build()

        val retrofit = Retrofit.Builder()
            .baseUrl("$normalized/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        return retrofit.create(FieldCheckApi::class.java).also {
            cachedApi = it
            cachedBaseUrl = normalized
        }
    }
}
