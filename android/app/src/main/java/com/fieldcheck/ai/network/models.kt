package com.fieldcheck.ai.network

import com.google.gson.annotations.SerializedName

/** Mirrors app/schemas/inspection.py::UploadResponse */
data class UploadResponse(
    @SerializedName("inspection_id") val inspectionId: String,
    @SerializedName("status") val status: String,
    @SerializedName("message") val message: String? = null,
)

/** Mirrors app/schemas/inspection.py::AssetOut */
data class AssetOut(
    @SerializedName("asset_type") val assetType: String? = null,
    @SerializedName("manufacturer") val manufacturer: String? = null,
    @SerializedName("model_number") val modelNumber: String? = null,
    @SerializedName("serial_or_tag_number") val serialOrTagNumber: String? = null,
    @SerializedName("confidence_score") val confidenceScore: Double? = null,
)

/** Mirrors app/schemas/inspection.py::DefectOut */
data class DefectOut(
    @SerializedName("id") val id: String,
    @SerializedName("defect_type") val defectType: String,
    @SerializedName("severity") val severity: String,
    @SerializedName("location_description") val locationDescription: String? = null,
    @SerializedName("recommendation") val recommendation: String? = null,
)

/** Mirrors app/schemas/inspection.py::InspectionOut */
data class InspectionOut(
    @SerializedName("id") val id: String,
    @SerializedName("status") val status: String,
    @SerializedName("original_filename") val originalFilename: String,
    @SerializedName("inspector_name") val inspectorName: String? = null,
    @SerializedName("inspector_email") val inspectorEmail: String? = null,
    @SerializedName("site_location") val siteLocation: String? = null,
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("error_message") val errorMessage: String? = null,
    @SerializedName("overall_condition") val overallCondition: String? = null,
    @SerializedName("overall_summary") val overallSummary: String? = null,
    @SerializedName("is_compliant") val isCompliant: Boolean? = null,
    @SerializedName("safety_hazards_detected") val safetyHazardsDetected: List<String>? = null,
    @SerializedName("immediate_action_required") val immediateActionRequired: Boolean? = null,
    @SerializedName("asset") val asset: AssetOut? = null,
    @SerializedName("defects") val defects: List<DefectOut> = emptyList(),
    @SerializedName("email_status") val emailStatus: String? = null,
    @SerializedName("image_url") val imageUrl: String? = null,
)
