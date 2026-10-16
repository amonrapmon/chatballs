from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connection

from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.comment_services import create_comment
from chatballs.conversations.comment_test_base import CommentTransactionTestBase
from chatballs.tenancy.database import tenant_atomic


class CommentConcurrencyTests(CommentTransactionTestBase):
    def test_concurrent_runtime_retries_create_one_record(self):
        from chatballs.tenancy.context import TenantContext

        context = TenantContext.for_membership(self.membership)
        operation = uuid4()
        ready = Barrier(2)

        def append():
            close_old_connections()
            try:
                with tenant_atomic(context), connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                    ready.wait(timeout=10)
                    comment, created = create_comment(
                        context=context, conversation_id=self.conversation.pk,
                        audience="INTERNAL", text="Concurrent comment", operation_id=operation,
                    )
                    return comment.pk, created
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: append(), range(2)))
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertCountEqual([created for _, created in results], [True, False])
        self.assertEqual(ConversationComment.objects.count(), 1)
