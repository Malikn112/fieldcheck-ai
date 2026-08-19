package com.fieldcheck.ai.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fieldcheck.ai.data.UserPreferences
import com.fieldcheck.ai.network.InspectionOut
import com.fieldcheck.ai.network.NetworkModule

@Composable
fun HistoryScreen(onOpenInspection: (String) -> Unit, onBack: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { UserPreferences(context) }
    val baseUrl by prefs.baseUrl.collectAsState(initial = UserPreferences.DEFAULT_BASE_URL)

    var items by remember { mutableStateOf<List<InspectionOut>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(baseUrl) {
        loading = true
        error = null
        try {
            items = NetworkModule.apiFor(baseUrl).listInspections(20)
        } catch (e: Exception) {
            error = "Could not load history: ${e.message}"
        }
        loading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Recent Inspections") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize(),
        ) {
            when {
                loading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                error != null -> Text(error.orEmpty(), modifier = Modifier.padding(16.dp))
                items.isEmpty() -> Text("No inspections yet.", modifier = Modifier.padding(16.dp))
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(items) { item ->
                        ListItem(
                            headlineContent = { Text(item.asset?.assetType ?: item.originalFilename) },
                            supportingContent = { Text(item.status) },
                            modifier = Modifier.clickable { onOpenInspection(item.id) },
                        )
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}
