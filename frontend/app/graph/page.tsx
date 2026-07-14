import KnowledgeGraphExplorer from "@/components/knowledge-graph-explorer"

export default function GraphPage() {
  return (
    <main className="container mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold mb-8 text-gray-900 dark:text-white">
        Knowledge Graph Explorer
      </h1>
      <KnowledgeGraphExplorer />
    </main>
  )
}
