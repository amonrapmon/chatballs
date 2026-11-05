# VK Native Mirror: upstream compatibility checklist

**Branch:** `feat/vk-native-mirror`. **Status:** tested in isolated PostgreSQL, not yet validated against live VK.

| Integration seam | VK Mirror addition | Disabled/default behavior | Focused tests |
| --- | --- | --- | --- |
| `conversations/transports/vk.py` | Extract typed `message_reply` from the same Long Poll | Client `message_new` remains stock inbound | `test_vk_transport.py` |
| `conversations/poller.py` | Dispatch typed VK reply; preserve `ts` on error | Non-VK pollers unchanged | `test_poll_backoff.py` |
| `conversations/transports/vk_send.py` | Store `messages.send` ID as own `SELF_ECHO` receipt | VK public sender still returns `bool`; no extra Long Poll | `test_vk_transport.py`, `test_vk_persistence.py` |
| `conversations/operator_messages.py` | Serialize deferred VK send and echo registration by Conversation lock | TG/MAX/email send paths unchanged | VK mirror targeted flow |
| `native_mirror/service.py` | VK bot_id source and anonymous technical `VK Native` origin; known self-echo before revision | Gateway still requires verified staff membership | `test_vk_persistence.py`, `test_persistence.py` |
| `native_mirror/replay.py` | VK pending receipt can replay with technical null author | Gateway replay still verifies real author | `test_vk_persistence.py` |
| `conversations/serializers.py` | Display `VK Native` only for private nativeOrigin marker | Other operator author names unchanged | `test_vk_persistence.py` |

Fork code resides in `native_mirror/{vk_adapter,vk_outbound}.py`; no new tables,
VK callback transport, `intercom-gw` changes, or VK employee attribution.

**Before upstream merge:** review these hooks and rerun the isolated workflow
`.github/workflows/vk-native-mirror.yml`. **Before live ENABLED:** confirm
`message_reply` and `messages.send` provider IDs from the test VK community,
one poller per community, and the own-send race in practice. Never enable on
the first production VK channel as an untested rollout.
