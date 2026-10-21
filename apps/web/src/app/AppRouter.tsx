import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./AppShell";
import { NotFound } from "./NotFound";

import { OverviewPage } from "../features/overview/OverviewPage";
import { NewsExplorer } from "../features/news/NewsExplorer";
import { NewsDetailPage } from "../features/news/NewsDetail";
import { SentimentPage } from "../features/sentiment/SentimentPage";
import { EntityList } from "../features/entities/EntityList";
import { EntityPage } from "../features/entities/EntityPage";
import { EventExplorer } from "../features/events/EventExplorer";
import { EventDetailPage } from "../features/events/EventDetail";
import { NarrativesPage } from "../features/narratives/NarrativesPage";
import { ModelLab } from "../features/research/ModelLab";
import { LeaderboardPage } from "../features/research/Leaderboard";
import { EvaluationPage } from "../features/research/Evaluation";
import { CopilotPage } from "../features/copilot/CopilotPage";
import { AnalyzePlayground } from "../features/playground/AnalyzePlayground";

/**
 * Route map.
 *
 * /                       Overview
 * /news                   News explorer
 * /news/:articleId        Article detail
 * /sentiment              Coverage-language trends
 * /entities               Entity directory
 * /entities/:entityId     Entity page
 * /events                 Event explorer
 * /events/:eventId        Event detail
 * /narratives             Narratives + watchlists
 * /research               Model lab
 * /research/leaderboard   Leaderboard
 * /research/evaluation    Evaluation summary
 * /copilot                Copilot Q&A
 * /playground             Analyze playground
 * *                       Not found
 */
export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="news" element={<NewsExplorer />} />
        <Route path="news/:articleId" element={<NewsDetailPage />} />
        <Route path="sentiment" element={<SentimentPage />} />
        <Route path="entities" element={<EntityList />} />
        <Route path="entities/:entityId" element={<EntityPage />} />
        <Route path="events" element={<EventExplorer />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />
        <Route path="narratives" element={<NarrativesPage />} />
        <Route path="research" element={<ModelLab />} />
        <Route path="research/leaderboard" element={<LeaderboardPage />} />
        <Route path="research/evaluation" element={<EvaluationPage />} />
        <Route path="copilot" element={<CopilotPage />} />
        <Route path="playground" element={<AnalyzePlayground />} />
        <Route path="overview" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
