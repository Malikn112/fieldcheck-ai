package com.fieldcheck.ai.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Mirrors the web dashboard's Tailwind blue-600 accent color.
private val Blue600 = Color(0xFF2563EB)
private val Blue700 = Color(0xFF1D4ED8)
private val Gray50 = Color(0xFFF9FAFB)

private val LightColors = lightColorScheme(
    primary = Blue600,
    onPrimary = Color.White,
    secondary = Blue700,
    background = Gray50,
)

private val DarkColors = darkColorScheme(
    primary = Blue600,
    onPrimary = Color.White,
)

@Composable
fun FieldCheckTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) DarkColors else LightColors
    MaterialTheme(colorScheme = colors, content = content)
}
