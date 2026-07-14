"use client";

import { useState } from "react";
import { KnowledgeGraphExplorer } from "@/components/knowledge-graph-explorer";
import { PredictionDashboard } from "@/components/prediction-dashboard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  const [activeDisease, setActiveDisease] = useState<string>("EFO_0000519");

  const diseases = [
    { id: "EFO_0000519", name: "Glioblastoma" },
    { id: "EFO_0000621", name: "Neuroblastoma" },
    { id: "EFO_0002559", name: "Medulloblastoma" },
    { id: "EFO_0000400", name: "Ewing Sarcoma" },
    { id: "EFO_0003165", name: "DIPG" },
  ];

  return (
    <main className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">NeuroDrug AI Platform</h1>
          <p className="text-muted-foreground">
            Heterogeneous Graph Neural Network framework for rare cancer drug repurposing.
          </p>
        </div>

        {/* Disease selector */}
        <div className="flex gap-2 flex-wrap">
          {diseases.map((d) => (
            <button
              key={d.id}
              onClick={() => setActiveDisease(d.id)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                activeDisease === d.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {d.name}
            </button>
          ))}
        </div>

        <Tabs defaultValue="explorer" className="space-y-4">
          <TabsList>
            <TabsTrigger value="explorer">Knowledge Graph Explorer</TabsTrigger>
            <TabsTrigger value="predictions">Drug Predictions</TabsTrigger>
            <TabsTrigger value="training">Model Training</TabsTrigger>
            <TabsTrigger value="evidence">Evidence Validation</TabsTrigger>
          </TabsList>

          <TabsContent value="explorer" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Multi-Omics Knowledge Graph</CardTitle>
                <CardDescription>
                  Explore gene-disease-drug relationships integrated from STRING, Open Targets, DGIdb, and TCGA.
                </CardDescription>
              </CardHeader>
              <CardContent className="h-[600px]">
                <KnowledgeGraphExplorer diseaseId={activeDisease} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="predictions" className="space-y-4">
            <PredictionDashboard diseaseId={activeDisease} />
          </TabsContent>

          <TabsContent value="training" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Model Training Center</CardTitle>
                <CardDescription>Launch HGT training jobs, monitor convergence, and compare baseline models.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Connect to /api/v1/training endpoints to manage experiments.</p>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="evidence" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Evidence Validation Center</CardTitle>
                <CardDescription>Cross-reference predictions against PubMed, ClinicalTrials.gov, and pathway databases.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Validation pipeline runs automatically after each prediction batch.</p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}
