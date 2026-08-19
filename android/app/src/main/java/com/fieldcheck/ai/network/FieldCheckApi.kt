package com.fieldcheck.ai.network

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** Matches app/api/v1/endpoints/inspections.py exactly. */
interface FieldCheckApi {

    @Multipart
    @POST("api/v1/inspections/upload")
    suspend fun uploadInspection(
        @Part file: MultipartBody.Part,
        @Part("inspector_name") inspectorName: RequestBody?,
        @Part("inspector_email") inspectorEmail: RequestBody?,
        @Part("site_location") siteLocation: RequestBody?,
        @Part("notes") notes: RequestBody?,
    ): UploadResponse

    @GET("api/v1/inspections/{id}")
    suspend fun getInspection(@Path("id") id: String): InspectionOut

    @GET("api/v1/inspections")
    suspend fun listInspections(@Query("limit") limit: Int = 20): List<InspectionOut>
}
