import { useState } from "react";
import { ApiError } from "../../api/client";
import { usePagedResource } from "../../shared/usePagedResource";
import { listSkills } from "./model";
export function useSkillsList(query = "", agentId = "") {
  const [forbidden, setForbidden] = useState(false);
  const resource = usePagedResource(
    async (page) => {
      try {
        const result = await listSkills(page, query, agentId);
        setForbidden(false);
        return result;
      } catch (error) {
        setForbidden(error instanceof ApiError && error.status === 403);
        throw error;
      }
    },
    [query, agentId],
  );
  return { ...resource, forbidden };
}
