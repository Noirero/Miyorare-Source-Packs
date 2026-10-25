package miyorare.kotatsuredo.ksp

import com.google.devtools.ksp.processing.CodeGenerator
import com.google.devtools.ksp.processing.Dependencies
import com.google.devtools.ksp.processing.KSPLogger
import com.google.devtools.ksp.processing.Resolver
import com.google.devtools.ksp.processing.SymbolProcessor
import com.google.devtools.ksp.processing.SymbolProcessorEnvironment
import com.google.devtools.ksp.processing.SymbolProcessorProvider
import com.google.devtools.ksp.symbol.KSAnnotated
import com.google.devtools.ksp.symbol.KSClassDeclaration
import com.google.devtools.ksp.validate

/**
 * Generates only the tiny Tsuki 1.0.5 entry surface consumed by Miyorare.
 * The actual Kotatsu-Redo implementation stays in its relocated private namespace.
 */
class MiyorareFacadeProcessorProvider : SymbolProcessorProvider {
    override fun create(environment: SymbolProcessorEnvironment): SymbolProcessor =
        MiyorareFacadeProcessor(environment.codeGenerator, environment.logger)
}

private class MiyorareFacadeProcessor(
    private val codeGenerator: CodeGenerator,
    private val logger: KSPLogger,
) : SymbolProcessor {

    private var generated = false

    override fun process(resolver: Resolver): List<KSAnnotated> {
        val symbols = resolver
            .getSymbolsWithAnnotation(ANNOTATION)
            .filterIsInstance<KSClassDeclaration>()
            .toList()
        val deferred = symbols.filterNot { it.validate() }
        if (generated || symbols.isEmpty()) return deferred
        if (deferred.isNotEmpty()) return deferred

        val entries = symbols.map(::entry).sortedBy(SourceEntry::name)
        require(entries.isNotEmpty()) { "Kotatsu facade has no parser sources" }
        require(entries.map(SourceEntry::name).distinct().size == entries.size) {
            "Kotatsu facade contains duplicate source names"
        }

        val dependencies = Dependencies.ALL_FILES
        codeGenerator.createNewFile(dependencies, "tsuki.model", "MangaParserSource").bufferedWriter().use { out ->
            out.appendLine("package tsuki.model")
            out.appendLine()
            out.appendLine("public enum class MangaParserSource(")
            out.appendLine("    override val title: String,")
            out.appendLine("    override val locale: String,")
            out.appendLine("    override val contentType: ContentType,")
            out.appendLine("    override val isBroken: Boolean,")
            out.appendLine("): MangaSource {")
            entries.forEach { item ->
                out.append("    ").append(item.name)
                    .append("(\"").append(escape(item.title)).append("\", \"")
                    .append(escape(item.locale)).append("\", ContentType.")
                    .append(item.contentType).append(", ").append(item.isBroken.toString()).appendLine("),")
            }
            out.appendLine("    ;")
            out.appendLine("}")
        }
        codeGenerator.createNewFile(dependencies, "tsuki", "MangaParserFactory").bufferedWriter().use { out ->
            out.appendLine("package tsuki")
            out.appendLine()
            out.appendLine("import tsuki.model.MangaParserSource")
            out.appendLine()
            out.appendLine("public fun newParser(source: MangaParserSource, context: MangaLoaderContext): MangaParser =")
            out.appendLine("    miyorare.kotatsuredo.bridge.newAdapterParser(source.name, context)")
        }
        generated = true
        logger.info("Generated Miyorare Kotatsu facade for ${entries.size} sources")
        return emptyList()
    }

    private fun entry(declaration: KSClassDeclaration): SourceEntry {
        val annotation = declaration.annotations.single { it.shortName.asString() == "MangaSourceParser" }
        fun argument(name: String): Any? = annotation.arguments.single { it.name?.asString() == name }.value
        val contentType = argument("type").toString().substringAfterLast('.')
        require(contentType.matches(Regex("[A-Z_]+"))) { "Invalid content type for ${declaration.simpleName.asString()}: $contentType" }
        return SourceEntry(
            name = argument("name") as String,
            title = argument("title") as String,
            locale = argument("locale") as String,
            contentType = contentType,
            isBroken = declaration.annotations.any { it.shortName.asString() == "Broken" },
        )
    }

    private fun escape(value: String): String = value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")

    private data class SourceEntry(
        val name: String,
        val title: String,
        val locale: String,
        val contentType: String,
        val isBroken: Boolean,
    )

    private companion object {
        const val ANNOTATION = "miyorare.kotatsuredo.MangaSourceParser"
    }
}
