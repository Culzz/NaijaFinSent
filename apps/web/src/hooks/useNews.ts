import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryKeys } from "./queryKeys";
import type { NewsDetail, NewsFilters, NewsListItem, Page } from "../lib/schemas";

/** Paged news list with filters. Keeps the previous page visible while loading. */
export function useNews(filters: NewsFilters): UseQueryResult<Page<NewsListItem>, Error> {
  return useQuery({
    queryKey: queryKeys.news.list(filters),
    queryFn: ({ signal }) => api.news(filters, { signal }),
    placeholderData: (previous) => previous,
  });
}

/** Single article with entity/event/evidence/relation detail. */
export function useNewsItem(
  articleId: string | undefined,
): UseQueryResult<NewsDetail, Error> {
  return useQuery({
    queryKey: queryKeys.news.detail(articleId ?? "none"),
    queryFn: ({ signal }) => api.newsItem(articleId as string, { signal }),
    enabled: Boolean(articleId),
  });
}
