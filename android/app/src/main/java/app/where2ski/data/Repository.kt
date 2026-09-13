package app.where2ski.data

import android.content.Context
import app.where2ski.BuildConfig
import java.io.File
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request

class Repository(private val context: Context) {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }
    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val cacheFile: File get() = File(context.filesDir, "latest.json")

    suspend fun loadCached(): Latest? = withContext(Dispatchers.IO) {
        runCatching {
            if (cacheFile.exists()) json.decodeFromString<Latest>(cacheFile.readText()) else null
        }.getOrNull()
    }

    suspend fun refresh(): Result<Latest> = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder()
                .url(BuildConfig.DATA_BASE_URL + "latest.json")
                .header("User-Agent", "where2ski-android/" + BuildConfig.VERSION_NAME)
                .build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) error("HTTP ${response.code}")
                val body = response.body?.string() ?: error("empty response")
                val parsed = json.decodeFromString<Latest>(body)
                cacheFile.writeText(body)
                parsed
            }
        }
    }
}
