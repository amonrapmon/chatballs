"""Received scores and sent-request cohorts deliberately have separate bases."""

from chatballs.ratings.results import scale_identity


def rating_summaries(rows, requests, cutoff):
    groups = {}

    def group_for(scale):
        key = scale_identity(scale)
        return groups.setdefault(key, {
            "scaleId": key, "scale": scale, "ratingCount": 0, "meanValue": None,
            "commentCount": 0, "periodBasis": "received_at",
            "distribution": [{"value": choice["value"], "label": choice["label"], "count": 0, "rate": None}
                             for choice in scale],
            "delivery": {"periodBasis": "sent_at", "answeredBefore": cutoff.isoformat(),
                         "sentCount": 0, "answeredCount": 0, "responseRate": None},
        })

    for row in rows:
        group = group_for(row["scale"])
        group["ratingCount"] += 1
        group["commentCount"] += bool(row["comment"].strip())
        for bucket in group["distribution"]:
            if bucket["value"] == row["value"]:
                bucket["count"] += 1
    for request in requests:
        delivery = group_for(request.scale)["delivery"]
        delivery["sentCount"] += 1
        result = getattr(request, "result", None)
        delivery["answeredCount"] += bool(result and result.received_at < cutoff)
    for group in groups.values():
        count = group["ratingCount"]
        if count:
            group["meanValue"] = sum(bucket["value"] * bucket["count"]
                                     for bucket in group["distribution"]) / count
            for bucket in group["distribution"]:
                bucket["rate"] = bucket["count"] / count
        delivery = group["delivery"]
        if delivery["sentCount"]:
            delivery["responseRate"] = delivery["answeredCount"] / delivery["sentCount"]
    return list(groups.values())
