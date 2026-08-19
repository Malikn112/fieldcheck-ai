package com.fieldcheck.ai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fieldcheck.ai.data.UserPreferences
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { UserPreferences(context) }
    val scope = rememberCoroutineScope()
    val currentBaseUrl by prefs.baseUrl.collectAsState(initial = UserPreferences.DEFAULT_BASE_URL)
    val session by prefs.session.collectAsState(initial = null)

    var urlInput by remember(currentBaseUrl) { mutableStateOf(currentBaseUrl) }
    var saved by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
        ) {
            session?.let {
                Text("Signed in as ${it.name} (${it.email})", style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(20.dp))
            }

            Text("Backend server URL", style = MaterialTheme.typography.titleSmall)
            Text(
                "This phone can't reach \"localhost\" — enter your computer's LAN IP " +
                    "and port instead, e.g. http://192.168.1.42:8000. The Android " +
                    "emulator's alias for your computer's localhost is 10.0.2.2.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = urlInput,
                onValueChange = { urlInput = it; saved = false },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = {
                    scope.launch {
                        prefs.saveBaseUrl(urlInput)
                        saved = true
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Save")
            }
            if (saved) {
                Spacer(Modifier.height(8.dp))
                Text("Saved.", color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}
