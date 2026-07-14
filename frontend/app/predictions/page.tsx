import PredictionDashboard from "@/components/prediction-dashboard"

export default function PredictionsPage() {
  return (
    <main className="container mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold mb-8 text-gray-900 dark:text-white">
        Drug Repurposing Predictions
      </h1>
      <PredictionDashboard />
    </main>
  )
}
