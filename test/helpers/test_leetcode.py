import sys
from typing import Optional
from unittest import mock

import leetcode.models.graphql_data  # type: ignore
import leetcode.models.graphql_question_contributor  # type: ignore
import leetcode.models.graphql_question_detail  # type: ignore
import leetcode.models.graphql_question_solution  # type: ignore
import leetcode.models.graphql_question_topic_tag  # type: ignore
import leetcode.models.graphql_response  # type: ignore
import leetcode.models.problems  # type: ignore
import leetcode.models.stat  # type: ignore
import leetcode.models.stat_status_pair  # type: ignore
import pytest

import leetcode_anki.helpers.leetcode


@mock.patch("os.environ", mock.MagicMock(return_value={"LEETCODE_SESSION_ID": "test"}))
@mock.patch("leetcode.auth", mock.MagicMock())
class TestLeetcode:
    @pytest.mark.asyncio
    async def test_get_leetcode_api_client(self) -> None:
        assert leetcode_anki.helpers.leetcode._get_leetcode_api_client()

    @pytest.mark.asyncio
    @mock.patch("leetcode_anki.helpers.leetcode._get_leetcode_api_client")
    async def test_get_leetcode_task_handles(self, api_client: mock.Mock) -> None:
        problems = leetcode.models.problems.Problems(
            user_name="test",
            num_solved=1,
            num_total=1,
            ac_easy=1,
            ac_medium=1,
            ac_hard=1,
            frequency_high=1,
            frequency_mid=1,
            category_slug="test",
            stat_status_pairs=[
                leetcode.models.stat_status_pair.StatStatusPair(
                    stat=leetcode.models.stat.Stat(
                        question_id=1,
                        question__hide=False,
                        question__title="Test 1",
                        question__title_slug="test1",
                        is_new_question=False,
                        frontend_question_id=1,
                        total_acs=1,
                        total_submitted=1,
                    ),
                    difficulty="easy",
                    is_favor=False,
                    status="ac",
                    paid_only=False,
                    frequency=0.0,
                    progress=1,
                ),
            ],
        )
        api_client.return_value.api_problems_topic_get.return_value = problems

        assert list(leetcode_anki.helpers.leetcode.get_leetcode_task_handles()) == [
            ("algorithms", "Test 1", "test1"),
            ("database", "Test 1", "test1"),
            ("shell", "Test 1", "test1"),
            ("concurrency", "Test 1", "test1"),
        ]

    @pytest.mark.asyncio
    async def test_retry(self) -> None:
        decorator = leetcode_anki.helpers.leetcode.retry(
            times=3, exceptions=(RuntimeError,), delay=0.01
        )

        async def test() -> str:
            return "test"

        func = mock.Mock(side_effect=[RuntimeError, RuntimeError, test()])

        wrapper = decorator(func)

        await wrapper() == "test"

        func.call_count = 3


class TestLeetcodeData:
    _question_detail_singleton: Optional[
        leetcode.models.graphql_question_detail.GraphqlQuestionDetail
    ] = None
    _leetcode_data_singleton: Optional[
        leetcode_anki.helpers.leetcode.LeetcodeData
    ] = None

    @property
    def _question_details(
        self,
    ) -> leetcode.models.graphql_question_detail.GraphqlQuestionDetail:
        question_detail = self._question_detail_singleton

        if not question_detail:
            raise ValueError("Question detail must not be None")

        return question_detail

    @property
    def _leetcode_data(self) -> leetcode_anki.helpers.leetcode.LeetcodeData:
        leetcode_data = self._leetcode_data_singleton

        if not leetcode_data:
            raise ValueError("Leetcode data must not be None")

        return leetcode_data

    @mock.patch("diskcache.Cache", mock.Mock(side_effect=lambda _: {}))
    @mock.patch("os.path.exists", mock.Mock(return_value=True))
    @mock.patch("leetcode_anki.helpers.leetcode._get_leetcode_api_client")
    def setup(self, leetcode_api: leetcode.api.default_api.DefaultApi) -> None:
        self._question_detail_singleton = leetcode.models.graphql_question_detail.GraphqlQuestionDetail(
            freq_bar=1.1,
            question_id="1",
            question_frontend_id="1",
            bound_topic_id=1,
            title="test title",
            content="test content",
            translated_title="test",
            translated_content="test translated content",
            is_paid_only=False,
            difficulty="Hard",
            likes=1,
            dislikes=1,
            is_liked=False,
            similar_questions="{}",
            contributors=[
                leetcode.models.graphql_question_contributor.GraphqlQuestionContributor(
                    username="testcontributor",
                    profile_url="test://profile/url",
                    avatar_url="test://avatar/url",
                ),
            ],
            lang_to_valid_playground="{}",
            topic_tags=[
                leetcode.models.graphql_question_topic_tag.GraphqlQuestionTopicTag(
                    name="test tag",
                    slug="test-tag",
                    translated_name="translated test tag",
                    typename="test type name",
                )
            ],
            company_tag_stats="{}",
            code_snippets="{}",
            stats='{"totalSubmissionRaw": 1, "totalAcceptedRaw": 1}',
            hints=["test hint 1", "test hint 2"],
            solution=[
                leetcode.models.graphql_question_solution.GraphqlQuestionSolution(
                    id=1,
                    can_see_detail=False,
                    typename="test type name",
                ),
            ],
            status="ac",
            sample_test_case="test case",
            meta_data="{}",
            judger_available=False,
            judge_type="large",
            mysql_schemas="test schema",
            enable_run_code=False,
            enable_test_mode=False,
            env_info="{}",
        )
        self._leetcode_data_singleton = leetcode_anki.helpers.leetcode.LeetcodeData()

    def test_init(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

    @pytest.mark.asyncio
    async def test_get_description(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details
        assert (await self._leetcode_data.description("test")) == "test content"

    @pytest.mark.asyncio
    async def test_submissions(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details
        assert (await self._leetcode_data.submissions_total("test")) == 1
        assert (await self._leetcode_data.submissions_accepted("test")) == 1

    @pytest.mark.asyncio
    async def test_difficulty(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        self._leetcode_data._cache["test"].difficulty = "Easy"
        assert "Easy" in (await self._leetcode_data.difficulty("test"))

        self._leetcode_data._cache["test"].difficulty = "Medium"
        assert "Medium" in (await self._leetcode_data.difficulty("test"))

        self._leetcode_data._cache["test"].difficulty = "Hard"
        assert "Hard" in (await self._leetcode_data.difficulty("test"))

    @pytest.mark.asyncio
    async def test_paid(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        assert (await self._leetcode_data.paid("test")) is False

    @pytest.mark.asyncio
    async def test_problem_id(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        assert (await self._leetcode_data.problem_id("test")) == "1"

    @pytest.mark.asyncio
    async def test_likes(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        assert (await self._leetcode_data.likes("test")) == 1
        assert (await self._leetcode_data.dislikes("test")) == 1

    @pytest.mark.asyncio
    async def test_tags(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        assert (await self._leetcode_data.tags("test")) == ["test-tag"]

    @pytest.mark.asyncio
    async def test_freq_bar(self) -> None:
        self._leetcode_data._cache["test"] = self._question_details

        assert (await self._leetcode_data.freq_bar("test")) == 1.1

    @mock.patch("time.sleep", mock.Mock())
    @pytest.mark.asyncio
    async def test_get_problem_data(self) -> None:
        data = leetcode.models.graphql_data.GraphqlData(question=self._question_details)
        response = leetcode.models.graphql_response.GraphqlResponse(data=data)
        self._leetcode_data._api_instance.graphql_post.return_value = response

        assert (
            await self._leetcode_data._get_problem_data("test")
        ) == self._question_details

        assert self._leetcode_data._cache["test"] == self._question_details
