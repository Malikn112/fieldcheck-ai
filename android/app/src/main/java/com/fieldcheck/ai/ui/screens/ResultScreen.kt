package com.fieldcheck.ai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fieldcheck.ai.data.UserPreferences
import com.fieldcheck.ai.network.InspectionOut
import com.fieldcheck.ai.network.NetworkModule
import kotlinx.coroutines.delay

/** Polls GET /inspections/{id} until COMPLETED/FAILED, mirroring the web
 * dashboard's app.js pollForResult() logic. */
@Composable
fun ResultScreen(inspectionId: String, onNewInspection: () -> Unit) {
    val context = LocalContext.current
    val prefs = remember { UserPreferences(context) }
    val baseUrl by prefs.baseUrl.collectAsState(initial = UserPreferences.DEFAULT_BASE_URL)

    var inspection by remember { mutableStateOf<InspectionOut?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(inspectionId, baseUrl) {
        val api = NetworkModule.apiFor(baseUrl)
        var attempts = 0
        // ~2 minutes of polling at a 2s interval, matching the web
        // frontend's POLL_TIMEOUT_MS / POLL_INTERVAL_MS.
        while (attempts < 60) {
            try {
                val result = api.getInspection(inspectionId)
                inspection = result
                if (result.status == "COMPLETED" || result.status == "FAILED") break
            } catch (e: Exception) {
                error = "Could not reach backend: ${e.message}"
                break
            }
            attempts++
            delay(2000)
        }
    }

    Scaffold(topBar = { TopAppBar(title = { Text("Inspection Result") }) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
                .fillMaxSize(),
        ) {
            val current = inspection
            when {
                error != null -> Text(error.orEmpty(), color = MaterialTheme.colorScheme.error)
                current == null -> LoadingRow("Loading…")
                current.status == "PENDING" -> LoadingRow("Queued for analysis…")
                current.status == "PROCESSING" -> LoadingRow("AI vision model is analyzing the asset…")
                current.status == "FAILED" -> {
                    Text("Analysis failed", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(8.dp))
                    Text(current.errorMessage ?: "Unknown error.", color = MaterialTheme.colorScheme.error)
                }
                else -> CompletedResult(current)
            }

            Spacer(Modifier.height(24.dp))
            Button(onClick = onNewInspection, modifier = Modifier.fillMaxWidth()) {
                Text("New Inspection")
            }
        }
    }
}

@Composable
private fun LoadingRow(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
        Spacer(Modifier.width(12.dp))
        Text(text)
    }
}

@Composable
private fun CompletedResult(current: InspectionOut) {
    val pass = current.overallCondition == "GOOD" || current.overallCondition == "ACCEPTABLE"

    Text(
        current.asset?.assetType ?: "Unknown Asset",
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
    )
    Text("ID: ${current.id}", style = MaterialTheme.typography.labelSmall)
    Spacer(Modifier.height(8.dp))

    Row(verticalAlignment = Alignment.CenterVertically) {
        AssistChip(onClick = {}, label = { Text(current.overallCondition ?: "N/A") })
        Spacer(Modifier.width(8.dp))
        Text(
            if (pass) "PASS" else "FAIL",
            color = if (pass) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            fontWeight = FontWeight.Bold,
        )
    }

    Spacer(Modifier.height(16.dp))
    Text("Summary", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
    Text(current.overallSummary ?: "No summary available.")

    Spacer(Modifier.height(16.dp))
    Text("Extracted Specs", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
    Text("Manufacturer: ${current.asset?.manufacturer ?: "—"}")
    Text("Model: ${current.asset?.modelNumber ?: "—"}")
    Text("Serial / Tag: ${current.asset?.serialOrTagNumber ?: "—"}")
    current.asset?.confidenceScore?.let { Text("Confidence: ${(it * 100).toInt()}%") }

    Spacer(Modifier.height(16.dp))
    Text(
        "Detected Defects (${current.defects.size})",
        style = MaterialTheme.typography.titleSmall,
        fontWeight = FontWeight.Bold,
    )
    if (current.defects.isEmpty()) {
        Text("No visual defects detected.")
    } else {
        current.defects.forEach { defect ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text("${defect.defectType} — ${defect.severity}", fontWeight = FontWeight.Bold)
                    Text("Location: ${defect.locationDescription ?: "—"}")
                    Text("Recommendation: ${defect.recommendation ?: "—"}")
                }
            }
        }
    }

    Spacer(Modifier.height(16.dp))
    Text("Safety & Compliance", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
    Text("Compliant: ${current.isCompliant?.let { if (it) "Yes" else "No" } ?: "—"}")
    Text("Immediate action required: " + if (current.immediateActionRequired == true) "YES — ESCALATE" else "No")
    current.safetyHazardsDetected?.forEach { Text("• $it") }

    current.emailStatus?.takeIf { it != "NOT_REQUESTED" }?.let {
        Spacer(Modifier.height(8.dp))
        Text("Report email: $it", style = MaterialTheme.typography.labelSmall)
    }
}
