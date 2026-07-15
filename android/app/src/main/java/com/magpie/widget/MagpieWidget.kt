package com.magpie.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.magpie.MainActivity
import com.magpie.data.local.SnapshotStore
import com.magpie.data.remote.MonthlySummaryOut
import com.magpie.util.formatCents
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

/** Hilt can't inject Glance objects; the widget pulls the snapshot store via an EntryPoint. */
@EntryPoint
@InstallIn(SingletonComponent::class)
interface WidgetEntryPoint {
    fun snapshotStore(): SnapshotStore
}

private fun entryPoint(context: Context): WidgetEntryPoint =
    EntryPointAccessors.fromApplication(context.applicationContext, WidgetEntryPoint::class.java)

/** The fields the widget needs — decoded from the Home snapshot (extra fields ignored). */
@Serializable
private data class WidgetData(
    val summary: MonthlySummaryOut,
    val safeToSpendCents: Long? = null,
    val reviewCount: Int = 0,
)

private val widgetJson = Json { ignoreUnknownKeys = true }

class MagpieWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = MagpieWidget()
}

/**
 * The home-screen money glance: this month's net + safe-to-spend + how many transactions await
 * review. Reads the app's last-known Home snapshot (no network of its own), so it shows the same
 * truth as the app — offline included. Tap to open Magpie.
 */
class MagpieWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val raw = entryPoint(context).snapshotStore().read(SnapshotStore.HOME)
        val data = raw?.let { runCatching { widgetJson.decodeFromString<WidgetData>(it) }.getOrNull() }
        provideContent {
            GlanceTheme { WidgetBody(data) }
        }
    }
}

// PULSE-adjacent colors, hardcoded: Glance can't consume the Compose theme objects.
private val InkBg = Color(0xFF10151A)
private val Teal = Color(0xFF35C2A6)
private val Green = Color(0xFF4ED08A)
private val Red = Color(0xFFE0616A)
private val TextPrimary = Color(0xFFE7EAF0)
private val TextDim = Color(0xFF9AA3B2)

@Composable
private fun WidgetBody(data: WidgetData?) {
    Column(
        modifier = GlanceModifier
            .fillMaxSize()
            .background(ColorProvider(InkBg))
            .padding(14.dp)
            .clickable(actionStartActivity<MainActivity>()),
    ) {
        Text(
            "Magpie",
            style = TextStyle(color = ColorProvider(Teal), fontSize = 14.sp, fontWeight = FontWeight.Bold),
        )
        Spacer(GlanceModifier.height(6.dp))
        if (data == null) {
            Text(
                "Open Magpie to sync",
                style = TextStyle(color = ColorProvider(TextDim), fontSize = 13.sp),
            )
            return@Column
        }
        Text("Net this month", style = TextStyle(color = ColorProvider(TextDim), fontSize = 12.sp))
        Text(
            formatCents(data.summary.netCents),
            style = TextStyle(
                color = ColorProvider(if (data.summary.netCents >= 0) Green else Red),
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
            ),
        )
        Spacer(GlanceModifier.height(8.dp))
        Row(modifier = GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("Safe to spend", style = TextStyle(color = ColorProvider(TextDim), fontSize = 12.sp))
                Text(
                    data.safeToSpendCents?.let { formatCents(it) } ?: "—",
                    style = TextStyle(color = ColorProvider(TextPrimary), fontSize = 15.sp, fontWeight = FontWeight.Medium),
                )
            }
            Spacer(GlanceModifier.defaultWeight())
            if (data.reviewCount > 0) {
                Text(
                    "${data.reviewCount} to review",
                    style = TextStyle(color = ColorProvider(Teal), fontSize = 13.sp),
                )
            }
        }
    }
}
