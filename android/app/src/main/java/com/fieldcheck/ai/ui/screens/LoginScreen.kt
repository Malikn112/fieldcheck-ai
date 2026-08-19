package com.fieldcheck.ai.ui.screens

import android.util.Patterns
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Engineering
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.fieldcheck.ai.data.UserPreferences
import kotlinx.coroutines.launch

/**
 * "Login" is intentionally simple: a name + email, persisted locally, no
 * password, no server-side session. It exists to label inspections
 * (inspector_name) and to address the auto-emailed report
 * (inspector_email) — not to gate access to the app.
 */
@Composable
fun LoginScreen(onLoggedIn: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { UserPreferences(context) }
    val scope = rememberCoroutineScope()

    val existingSession by prefs.session.collectAsState(initial = null)

    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }

    // A returning inspector with a saved session skips straight past login.
    LaunchedEffect(existingSession) {
        if (existingSession != null) onLoggedIn()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(Icons.Filled.Engineering, contentDescription = null, modifier = Modifier.size(48.dp))
        Spacer(Modifier.height(12.dp))
        Text("FieldCheck AI", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(
            "Automated Industrial Asset Inspection",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it; error = null },
            label = { Text("Your name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it; error = null },
            label = { Text("Your email") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
        )

        error?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                val trimmedName = name.trim()
                val trimmedEmail = email.trim()
                if (trimmedName.isEmpty()) {
                    error = "Please enter your name."
                    return@Button
                }
                if (!Patterns.EMAIL_ADDRESS.matcher(trimmedEmail).matches()) {
                    error = "Please enter a valid email address."
                    return@Button
                }
                scope.launch {
                    prefs.saveSession(trimmedName, trimmedEmail)
                    onLoggedIn()
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Continue")
        }

        Spacer(Modifier.height(8.dp))
        Text(
            "No password needed — this just labels your inspections and lets " +
                "completed reports be emailed to you.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
