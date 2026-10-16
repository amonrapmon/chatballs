"""Project server summaries into numeric file cells; never recalculate them."""

from chatballs.i18n import t

from .support_feedback_export_values import feedback_table, feedback_value


def summary_tables(sections):
    ratings = feedback_table(("section", "employee", "scaleId", "scale", "ratingCount", "meanValue",
                              "commentCount", "sentCount", "answeredCount", "responseRate", "answeredBefore"))
    distribution = feedback_table(("section", "employee", "scaleId", "value", "label", "valueCount", "rate"))
    quality = feedback_table(("section", "employee", "criteriaVersionId", "criteriaVersion", "validFrom", "validTo",
                              "analysisCount", "correctedAnalysisCount", "correctionRate", "code", "name",
                              "description", "scale", "scoredCount", "missingCount", "correctedCount",
                              "summaryKind", "positiveValue", "originalSummary", "effectiveSummary"))
    for section, employee, data in sections:
        for group in data["customerRatings"].get("scaleSummaries", []):
            delivery = group["delivery"]
            ratings.append([section, employee, group["scaleId"], feedback_value(group["scale"]),
                            group["ratingCount"], group["meanValue"], group["commentCount"],
                            delivery["sentCount"], delivery["answeredCount"], delivery["responseRate"],
                            delivery["answeredBefore"]])
            for bucket in group["distribution"]:
                distribution.append([section, employee, group["scaleId"], bucket["value"], bucket["label"],
                                     bucket["count"], bucket["rate"]])
        for version in data["qualityAnalysis"].get("versions", []):
            for criterion in version["criteria"]:
                summary = criterion["effectiveSummary"]
                quality.append([section, employee, version["criteriaVersionId"], version["criteriaVersion"],
                                version["validFrom"], version["validTo"], version["analysisCount"],
                                version["correctedAnalysisCount"], version["correctionRate"], criterion["code"],
                                criterion["name"], criterion["description"], feedback_value(criterion["scale"]),
                                criterion["scoredCount"], criterion["missingCount"], criterion["correctedCount"],
                                t(f"support_stats.summary.{summary['kind']}"), summary.get("positiveValue"),
                                criterion["originalSummary"]["value"], summary["value"]])
    return [("rating_summaries", ratings), ("rating_distribution", distribution), ("quality_summaries", quality)]
