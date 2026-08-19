package com.fieldcheck.ai.ui

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.fieldcheck.ai.ui.screens.CaptureScreen
import com.fieldcheck.ai.ui.screens.HistoryScreen
import com.fieldcheck.ai.ui.screens.LoginScreen
import com.fieldcheck.ai.ui.screens.ResultScreen
import com.fieldcheck.ai.ui.screens.SettingsScreen

object Routes {
    const val LOGIN = "login"
    const val CAPTURE = "capture"
    const val RESULT = "result/{inspectionId}"
    const val HISTORY = "history"
    const val SETTINGS = "settings"

    fun result(inspectionId: String) = "result/$inspectionId"
}

@Composable
fun FieldCheckNavHost(navController: NavHostController = rememberNavController()) {
    NavHost(navController = navController, startDestination = Routes.LOGIN) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate(Routes.CAPTURE) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
            )
        }
        composable(Routes.CAPTURE) {
            CaptureScreen(
                onUploaded = { inspectionId -> navController.navigate(Routes.result(inspectionId)) },
                onOpenHistory = { navController.navigate(Routes.HISTORY) },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onLogout = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                },
            )
        }
        composable(Routes.RESULT) { backStackEntry ->
            val inspectionId = backStackEntry.arguments?.getString("inspectionId")
            if (inspectionId != null) {
                ResultScreen(
                    inspectionId = inspectionId,
                    onNewInspection = {
                        navController.navigate(Routes.CAPTURE) {
                            popUpTo(Routes.CAPTURE) { inclusive = true }
                        }
                    },
                )
            }
        }
        composable(Routes.HISTORY) {
            HistoryScreen(
                onOpenInspection = { id -> navController.navigate(Routes.result(id)) },
                onBack = { navController.popBackStack() },
            )
        }
        composable(Routes.SETTINGS) {
            SettingsScreen(onBack = { navController.popBackStack() })
        }
    }
}
