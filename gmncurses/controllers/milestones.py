# -*- coding: utf-8 -*-

"""
gmncurses.controllers.milestone
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

from concurrent.futures import wait
import functools

from gmncurses.config import ProjectMilestoneKeys
from gmncurses.ui import signals
from gmncurses.ui.widgets.milestones import UserStoryEntry, TaskEntry
import gmncurses.data


from . import base


class ProjectMilestoneSubController(base.Controller):
    def __init__(self, view, executor, state_machine):
        self.view = view
        self.executor = executor
        self.state_machine = state_machine

    def handle(self, key):
        if key == ProjectMilestoneKeys.CREATE_USER_STORY:
            pass
        elif key == ProjectMilestoneKeys.CREATE_TASK:
            self.new_task()
        elif key == ProjectMilestoneKeys.EDIT_USER_STORY_OR_TASK:
            self.edit_user_story_or_task()
        elif key == ProjectMilestoneKeys.DELETE_USER_STORY_OR_TASK:
            self.delete_user_story_or_task()
        elif key == ProjectMilestoneKeys.CHANGE_TO_MILESTONE:
            self.change_to_milestone()
        elif key == ProjectMilestoneKeys.RELOAD:
            self.load()
        elif key == ProjectMilestoneKeys.HELP:
            self.help_info()
        else:
            super().handle(key)

    def load(self):
        self.state_machine.transition(self.state_machine.PROJECT_MILESTONES)

        self.view.notifier.info_msg("Fetching Stats and User stories")

        if hasattr(self, "milestone"):
            current_milestone = self.milestone
        else:
            current_milestone = gmncurses.data.current_milestone(self.view._project)

        milestone_f = self.executor.milestone(current_milestone, self.view._project)
        milestone_f.add_done_callback(self.handle_milestone)

        milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
        milestone_stats_f.add_done_callback(self.handle_milestone_stats)

        user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
        user_stories_f.add_done_callback(self.handle_user_stories)

        tasks_f = self.executor.tasks(current_milestone, self.view._project)
        tasks_f.add_done_callback(self.handle_tasks)

        futures = (tasks_f, user_stories_f)
        futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
        futures_completed_f.add_done_callback(functools.partial(self.handle_user_stories_and_task_info_fetched,
                                                                info_msg="User stories and tasks fetched",
                                                                error_msg="Failed to fetch milestone data "
                                                                           "(user stories or task)"))

    def new_task(self):
        selected_item = self.view.taskboard.widget.get_focus()

        if isinstance(selected_item, UserStoryEntry):
            task = {"user_story": selected_item.user_story.get("id", None)}
        elif isinstance(selected_item, TaskEntry):
            task = {"user_story": selected_item.task.get("user_story", None)}
        else:
            task = {"user_story": None}

        self.view.open_task_form(task=task)

        signals.connect(self.view.task_form.cancel_button, "click",
                lambda _: self.cancel_task_form())
        signals.connect(self.view.task_form.save_button, "click",
                lambda _: self.handler_create_task_request())

    def edit_user_story_or_task(self):
        selected_item = self.view.taskboard.widget.get_focus()

        if isinstance(selected_item, UserStoryEntry):
            self.view.open_user_story_form(user_story=selected_item.user_story)

            signals.connect(self.view.user_story_form.cancel_button, "click",
                    lambda _: self.cancel_user_story_form())
            signals.connect(self.view.user_story_form.save_button, "click",
                    lambda _: self.handler_edit_user_story_request(selected_item.user_story))
        elif isinstance(selected_item, TaskEntry):
            self.view.open_task_form(task=selected_item.task)

            signals.connect(self.view.task_form.cancel_button, "click",
                    lambda _: self.cancel_task_form())
            signals.connect(self.view.task_form.save_button, "click",
                    lambda _: self.handler_edit_task_request(selected_item.task))

    def cancel_user_story_form(self):
        self.view.close_user_story_form()

    def cancel_task_form(self):
        self.view.close_task_form()

    def delete_user_story_or_task(self):
        selected_item = self.view.taskboard.widget.get_focus()

        if isinstance(selected_item, UserStoryEntry):
            uss_delete_f = self.executor.delete_user_story(selected_item.user_story)
            uss_delete_f.add_done_callback(self.handler_delete_user_story_response)
        elif isinstance(selected_item, TaskEntry):
            task_delete_f = self.executor.delete_task(selected_item.task)
            task_delete_f.add_done_callback(self.handler_delete_task_response)

    def change_to_milestone(self):
        self.view.open_milestones_selector_popup(current_milestone=self.view._milestone)

        signals.connect(self.view.milestone_selector_popup.cancel_button, "click",
                        lambda _: self.cancel_milestone_selector_popup())

        for option in self.view.milestone_selector_popup.options:
            signals.connect(option, "click", functools.partial(self.handler_change_to_milestone))

    def cancel_milestone_selector_popup(self):
        self.view.close_milestone_selector_popup()

    def help_info(self):
        self.view.open_help_popup()

        signals.connect(self.view.help_popup.close_button, "click",
                lambda _: self.close_help_info())

    def close_help_info(self):
        self.view.close_help_popup()

    def handle_milestone(self, future):
        self.view._milestone = future.result()
        if self.view._milestone:
            self.view.info.populate(self.view._milestone)
            self.state_machine.refresh()

    def handle_milestone_stats(self, future):
        self.view._milestone_stats = future.result()
        if self.view._milestone_stats:
            self.view.stats.populate(self.view._milestone_stats)
            self.state_machine.refresh()

    def handle_user_stories(self, future):
        self.view._user_stories = future.result()

    def handle_tasks(self, future):
        self.view._tasks = future.result()

    def handle_user_stories_and_task_info_fetched(self, future_with_results, info_msg=None, error_msg=None):
        done, not_done = future_with_results.result()
        if len(done) == 2:
            self.view.taskboard.populate(self.view._user_stories, self.view._tasks)
            if info_msg:
                self.view.notifier.info_msg(info_msg)
            self.state_machine.refresh()
        else:
            # TODO retry failed operations
            if error_msg:
                self.view.notifier.error_msg(error_msg)

    def handler_create_task_request(self):
        data = self.view.get_task_form_data()

        if not data.get("subject", None):
            self.view.notifier.error_msg("Subject is required")
        else:
            task_post_f = self.executor.create_task(data)
            task_post_f.add_done_callback(self.handler_create_task_response)

    def handler_create_task_response(self, future):
        response = future.result()

        if response is None:
            self.view.notifier.error_msg("Create error")
        else:
            self.view.notifier.info_msg("Create successful!")
            self.view.close_task_form()

            if hasattr(self, "milestone"):
                current_milestone = self.milestone
            else:
                current_milestone = gmncurses.data.current_milestone(self.view._project)

            milestone_f = self.executor.milestone(current_milestone, self.view._project)
            milestone_f.add_done_callback(self.handle_milestone)

            milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
            milestone_stats_f.add_done_callback(self.handle_milestone_stats)

            user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
            user_stories_f.add_done_callback(self.handle_user_stories)

            tasks_f = self.executor.tasks(current_milestone, self.view._project)
            tasks_f.add_done_callback(self.handle_tasks)

            futures = (tasks_f, user_stories_f)
            futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
            futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

    def handler_edit_user_story_request(self, user_story):
        data = self.view.get_user_story_form_data()

        if not data.get("subject", None):
            self.view.notifier.error_msg("Subject is required")
        else:
            us_patch_f = self.executor.update_user_story(user_story, data)
            us_patch_f.add_done_callback(self.handler_edit_user_story_response)

    def handler_edit_user_story_response(self, future):
        response = future.result()

        if response is None:
            self.view.notifier.error_msg("Edit error")
        else:
            self.view.notifier.info_msg("Edit user_story successful!")
            self.view.close_user_story_form()

            if hasattr(self, "milestone"):
                current_milestone = self.milestone
            else:
                current_milestone = gmncurses.data.current_milestone(self.view._project)

            milestone_f = self.executor.milestone(current_milestone, self.view._project)
            milestone_f.add_done_callback(self.handle_milestone)

            milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
            milestone_stats_f.add_done_callback(self.handle_milestone_stats)

            user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
            user_stories_f.add_done_callback(self.handle_user_stories)

            tasks_f = self.executor.tasks(current_milestone, self.view._project)
            tasks_f.add_done_callback(self.handle_tasks)

            futures = (tasks_f, user_stories_f)
            futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
            futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

    def handler_edit_task_request(self, task):
        data = self.view.get_task_form_data()

        if not data.get("subject", None):
            self.view.notifier.error_msg("Subject is required")
        else:
            us_patch_f = self.executor.update_task(task, data)
            us_patch_f.add_done_callback(self.handler_edit_task_response)

    def handler_edit_task_response(self, future):
        response = future.result()

        if response is None:
            self.view.notifier.error_msg("Edit error")
        else:
            self.view.notifier.info_msg("Edit task successful!")
            self.view.close_task_form()

            if hasattr(self, "milestone"):
                current_milestone = self.milestone
            else:
                current_milestone = gmncurses.data.current_milestone(self.view._project)

            milestone_f = self.executor.milestone(current_milestone, self.view._project)
            milestone_f.add_done_callback(self.handle_milestone)

            milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
            milestone_stats_f.add_done_callback(self.handle_milestone_stats)

            user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
            user_stories_f.add_done_callback(self.handle_user_stories)

            tasks_f = self.executor.tasks(current_milestone, self.view._project)
            tasks_f.add_done_callback(self.handle_tasks)

            futures = (tasks_f, user_stories_f)
            futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
            futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

    def handler_delete_user_story_response(self, future):
        response = future.result()

        if response is None:
            self.view.notifier.error_msg("Error deleting user_story")
        else:
            self.view.notifier.info_msg("Delete user story")

            if hasattr(self, "milestone"):
                current_milestone = self.milestone
            else:
                current_milestone = gmncurses.data.current_milestone(self.view._project)

            milestone_f = self.executor.milestone(current_milestone, self.view._project)
            milestone_f.add_done_callback(self.handle_milestone)

            milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
            milestone_stats_f.add_done_callback(self.handle_milestone_stats)

            user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
            user_stories_f.add_done_callback(self.handle_user_stories)

            tasks_f = self.executor.tasks(current_milestone, self.view._project)
            tasks_f.add_done_callback(self.handle_tasks)

            futures = (tasks_f, user_stories_f)
            futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
            futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

    def handler_delete_task_response(self, future):
        response = future.result()

        if response is None:
            self.view.notifier.error_msg("Error deleting task")
        else:
            self.view.notifier.info_msg("Delete task")

            if hasattr(self, "milestone"):
                current_milestone = self.milestone
            else:
                current_milestone = gmncurses.data.current_milestone(self.view._project)

            milestone_f = self.executor.milestone(current_milestone, self.view._project)
            milestone_f.add_done_callback(self.handle_milestone)

            milestone_stats_f = self.executor.milestone_stats(current_milestone, self.view._project)
            milestone_stats_f.add_done_callback(self.handle_milestone_stats)

            user_stories_f = self.executor.user_stories(current_milestone, self.view._project)
            user_stories_f.add_done_callback(self.handle_user_stories)

            tasks_f = self.executor.tasks(current_milestone, self.view._project)
            tasks_f.add_done_callback(self.handle_tasks)

            futures = (tasks_f, user_stories_f)
            futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
            futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

    def handler_change_to_milestone(self, selected_option):
        self.view.notifier.info_msg("Change to milestone '{}'".format(selected_option.milestone["name"]))

        milestone = selected_option.milestone

        milestone_f = self.executor.milestone(milestone, self.view._project)
        milestone_f.add_done_callback(self.handle_milestone)

        milestone_stats_f = self.executor.milestone_stats(milestone, self.view._project)
        milestone_stats_f.add_done_callback(self.handle_milestone_stats)

        user_stories_f = self.executor.user_stories(milestone, self.view._project)
        user_stories_f.add_done_callback(self.handle_user_stories)

        tasks_f = self.executor.tasks(milestone, self.view._project)
        tasks_f.add_done_callback(self.handle_tasks)

        futures = (tasks_f, user_stories_f)
        futures_completed_f = self.executor.pool.submit(lambda : wait(futures, 10))
        futures_completed_f.add_done_callback(self.handle_user_stories_and_task_info_fetched)

        self.cancel_milestone_selector_popup()
