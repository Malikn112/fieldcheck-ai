package com.fieldcheck.ai.ui.screens

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import coil.compose.rememberAsyncImagePainter
import com.fieldcheck.ai.data.UserPreferences
import com.fieldcheck.ai.network.NetworkModule
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

/**
 * Camera capture + upload. Uses the system Camera app via
 * ActivityResultContracts.TakePicture() (writes the full-resolution photo
 * to a FileProvider-issued content:// URI) rather than CameraX, which keeps
 * this screen simple while still being a real on-device camera capture —
 * exactly what "take pictures on the field" requires.
 */
@Composable
fun CaptureScreen(
    onUploaded: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onOpenSettings: () -> Unit,
    onLogout: () -> Unit,
) {
    val context = LocalContext.current
    val prefs = remember { UserPreferences(context) }
    val scope = rememberCoroutineScope()
    val session by prefs.session.collectAsState(initial = null)
    val baseUrl by prefs.baseUrl.collectAsState(initial = UserPreferences.DEFAULT_BASE_URL)

    var photoUri by remember { mutableStateOf<Uri?>(null) }
    var photoFile by remember { mutableStateOf<File?>(null) }
    var siteLocation by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var isUploading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (!success) {
            photoUri = null
            photoFile = null
        }
    }

    fun launchCamera() {
        val file = createImageFile(context)
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        photoFile = file
        photoUri = uri
        takePicture.launch(uri)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("New Inspection") },
                actions = {
                    IconButton(onClick = onOpenHistory) {
                        Icon(Icons.Filled.History, contentDescription = "History")
                    }
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings")
                    }
                    IconButton(onClick = onLogout) {
                        Icon(Icons.Filled.Logout, contentDescription = "Log out")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
                .fillMaxSize(),
        ) {
            session?.let {
                Text("Signed in as ${it.name} (${it.email})", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(12.dp))
            }

            Card(
                onClick = { launchCamera() },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(220.dp),
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    val currentUri = photoUri
                    if (currentUri != null) {
                        Image(
                            painter = rememberAsyncImagePainter(currentUri),
                            contentDescription = "Captured photo",
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Crop,
                        )
                    } else {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Filled.CameraAlt, contentDescription = null, modifier = Modifier.size(40.dp))
                            Spacer(Modifier.height(8.dp))
                            Text("Tap to take a photo")
                        }
                    }
                }
            }

            Spacer(Modifier.height(16.dp))
            OutlinedTextField(
                value = siteLocation,
                onValueChange = { siteLocation = it },
                label = { Text("Site / location (optional)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it },
                label = { Text("Notes (optional)") },
                minLines = 2,
                modifier = Modifier.fillMaxWidth(),
            )

            error?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    val file = photoFile
                    val user = session
                    if (file == null || !file.exists()) {
                        error = "Take a photo first."
                        return@Button
                    }
                    if (user == null) {
                        error = "Session expired — please log in again."
                        return@Button
                    }
                    isUploading = true
                    error = null
                    scope.launch {
                        try {
                            val api = NetworkModule.apiFor(baseUrl)
                            val plainText = "text/plain".toMediaTypeOrNull()
                            val filePart = MultipartBody.Part.createFormData(
                                "file", file.name, file.asRequestBody("image/jpeg".toMediaTypeOrNull()),
                            )
                            val response = api.uploadInspection(
                                file = filePart,
                                inspectorName = user.name.toRequestBody(plainText),
                                inspectorEmail = user.email.toRequestBody(plainText),
                                siteLocation = siteLocation.takeIf { it.isNotBlank() }?.toRequestBody(plainText),
                                notes = notes.takeIf { it.isNotBlank() }?.toRequestBody(plainText),
                            )
                            isUploading = false
                            onUploaded(response.inspectionId)
                        } catch (e: Exception) {
                            isUploading = false
                            error = "Upload failed: ${e.message ?: "check your backend URL in Settings."}"
                        }
                    }
                },
                enabled = !isUploading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (isUploading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (isUploading) "Uploading…" else "Analyze Asset")
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "Backend: $baseUrl",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun createImageFile(context: Context): File {
    val dir = File(context.cacheDir, "images").apply { mkdirs() }
    return File(dir, "capture_${System.currentTimeMillis()}.jpg")
}
