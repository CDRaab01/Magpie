package com.magpie.ui.flow

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.magpie.ui.theme.MagpieTheme
import design.pulse.ui.components.Caption
import design.pulse.ui.components.PanelCard
import design.pulse.ui.components.SectionHeader
import java.text.DecimalFormat

/** Distinct, dark-friendly hues for the spend flows; Saved gets its own green. */
private val CategoryPalette = listOf(
    Color(0xFF5B8DEF), Color(0xFF9B7BF0), Color(0xFFE0A83A), Color(0xFFE86A8C),
    Color(0xFF3FB6C8), Color(0xFF7FBF5F), Color(0xFFE08A4A), Color(0xFF6C8CD5),
)
private val SavingsColor = Color(0xFF4ED08A)

private fun dollars(cents: Long): String = "$" + DecimalFormat("#,##0").format(cents / 100.0)

private fun colorFor(item: CashFlowItem, index: Int): Color =
    if (item.kind == FlowKind.SAVINGS) SavingsColor else CategoryPalette[index % CategoryPalette.size]

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CashFlowScreen(navController: NavController) {
    val viewModel: CashFlowViewModel = hiltViewModel()
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Cash flow", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when {
                state.loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                state.items.isEmpty() -> Text(
                    "No cash flow yet for ${state.monthLabel}.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
                else -> CashFlowContent(state.monthLabel, state.incomeCents, state.items)
            }
        }
    }
}

@Composable
internal fun CashFlowContent(monthLabel: String, incomeCents: Long, items: List<CashFlowItem>) {
    val colors = MagpieTheme.colors
    val saved = items.firstOrNull { it.kind == FlowKind.SAVINGS }?.cents ?: 0L
    val entries = items.mapIndexed { i, item -> item to colorFor(item, i) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        PanelCard(Modifier.fillMaxWidth()) {
            Column {
                Caption(monthLabel)
                Spacer(Modifier.height(8.dp))
                Row(Modifier.fillMaxWidth()) {
                    Column(Modifier.weight(1f)) {
                        Caption("Money in")
                        Text(dollars(incomeCents), style = MaterialTheme.typography.headlineSmall, color = colors.money.base)
                    }
                    Column(Modifier.weight(1f)) {
                        Caption("Saved")
                        Text(dollars(saved), style = MaterialTheme.typography.headlineSmall, color = SavingsColor)
                    }
                }
            }
        }

        PanelCard(Modifier.fillMaxWidth()) {
            Column {
                SectionHeader("Where it went", channel = colors.money.base)
                Spacer(Modifier.height(16.dp))
                SankeyChart(
                    entries = entries,
                    incomeColor = colors.money.base,
                    modifier = Modifier.fillMaxWidth().height(260.dp),
                )
                Spacer(Modifier.height(16.dp))
                entries.forEach { (item, color) ->
                    Row(
                        Modifier.fillMaxWidth().padding(vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(10.dp).clip(CircleShape).background(color))
                        Spacer(Modifier.width(10.dp))
                        Text(item.label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                        Text(
                            dollars(item.cents),
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (item.kind == FlowKind.SAVINGS) SavingsColor else MaterialTheme.colorScheme.onSurface,
                        )
                    }
                }
            }
        }
    }
}

/**
 * A horizontal Sankey: one Income source on the left flows out to each spending category (and what
 * was Saved) on the right, each ribbon's thickness proportional to its share of the money. Pure
 * Canvas — hues and structure only, meaning lives in the caller.
 */
@Composable
internal fun SankeyChart(
    entries: List<Pair<CashFlowItem, Color>>,
    incomeColor: Color,
    modifier: Modifier = Modifier,
) {
    val total = entries.sumOf { it.first.cents }.coerceAtLeast(1L)
    Canvas(modifier) {
        val h = size.height
        val w = size.width
        val nodeW = 14.dp.toPx()
        val gap = 4.dp.toPx()
        val n = entries.size
        val usableH = (h - gap * (n - 1).coerceAtLeast(0)).coerceAtLeast(1f)
        val radius = CornerRadius(4f, 4f)

        // Income source bar — full height, since all of it flows out.
        drawRoundRect(incomeColor, topLeft = Offset(0f, 0f), size = Size(nodeW, h), cornerRadius = radius)

        val x0 = nodeW
        val x1 = w - nodeW
        val cx = (x0 + x1) / 2f
        var targetY = 0f
        var sourceY = 0f
        entries.forEach { (item, color) ->
            val frac = item.cents / total.toFloat()
            val targetH = usableH * frac
            val sourceH = h * frac // the source is sliced with no gaps, so ribbons fill it fully

            // Ribbon: a band from the source slice to the target slice.
            val ribbon = Path().apply {
                moveTo(x0, sourceY)
                cubicTo(cx, sourceY, cx, targetY, x1, targetY)
                lineTo(x1, targetY + targetH)
                cubicTo(cx, targetY + targetH, cx, sourceY + sourceH, x0, sourceY + sourceH)
                close()
            }
            drawPath(ribbon, color.copy(alpha = 0.30f))

            // Target node bar.
            drawRoundRect(
                color,
                topLeft = Offset(x1, targetY),
                size = Size(nodeW, targetH),
                cornerRadius = radius,
            )

            targetY += targetH + gap
            sourceY += sourceH
        }
    }
}
