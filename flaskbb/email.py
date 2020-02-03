# -*- coding: utf-8 -*-
"""
    flaskbb.email
    ~~~~~~~~~~~~~

    This module adds the functionality to send emails

    :copyright: (c) 2014 by the FlaskBB Team.
    :license: BSD, see LICENSE for more details.
"""
import datetime
import logging
import smtplib
from threading import Thread

from flask import render_template, current_app
from flask_babelplus import lazy_gettext as _
from flaskbb.extensions import db

from flaskbb.extensions import mail, celery
from flaskbb.forum.models import Forum, Post, Topic, TopicsRead, topictracker
from flaskbb.user.models import User

logger = logging.getLogger(__name__)


@celery.task
def send_reset_token(token, username, email):
    """Sends the reset token to the user's email address.

    :param token: The token to send to the user
    :param username: The username to whom the email should be sent.
    :param email:  The email address of the user
    """
    send_email(
        subject=_("Password Recovery Confirmation"),
        recipients=[email],
        text_body=render_template(
            "email/reset_password.txt",
            username=username,
            token=token
        ),
        html_body=render_template(
            "email/reset_password.html",
            username=username,
            token=token
        )
    )


@celery.task
def send_activation_token(token, username, email):
    """Sends the activation token to the user's email address.

    :param token: The token to send to the user
    :param username: The username to whom the email should be sent.
    :param email:  The email address of the user
    """
    send_email(
        subject=_("Account Activation"),
        recipients=[email],
        text_body=render_template(
            "email/activate_account.txt",
            username=username,
            token=token
        ),
        html_body=render_template(
            "email/activate_account.html",
            username=username,
            token=token
        )
    )


@celery.task
def send_async_email(*args, **kwargs):
    send_email(*args, **kwargs)


def send_email(subject, recipients, text_body, html_body, sender=None):
    """Sends an email to the given recipients.

    :param subject: The subject of the email.
    :param recipients: A list of recipients.
    :param text_body: The text body of the email.
    :param html_body: The html body of the email.
    :param sender: A two-element tuple consisting of name and address.
                   If no sender is given, it will fall back to the one you
                   have configured with ``MAIL_DEFAULT_SENDER``.
    """
    print("sending email from sender", sender)
    sender=current_app.config["MAIL_DEFAULT_SENDER"]

    msg = 'Subject: {}\n\n{}'.format(subject, text_body)
    if current_app.config["MAIL_USE_SSL"] == True:
        smtp_func = smtplib.SMTP_SSL
    else:
        smtp_func = smtplib.SMTP
    print(msg)
    s = smtp_func(current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"])
    s.ehlo()
    #s.connect( )
    s.login(current_app.config["MAIL_USERNAME"],current_app.config["MAIL_PASSWORD"])
    s.sendmail(sender, recipients, msg)
    s.close()

class notify_user(celery.Task):
    def __init__(self):
        self.notification_scheduled = False
        self.last_notification = datetime.datetime.utcnow()
        self.countdown = 0 

    def on_message(self, ret):
        notify.notification_scheduled = False
        notify.last_notification = datetime.datetime.utcnow()
        print("on message set date:")

def __thd_notify():
    print("celry sched ...")
    r = __notify_users_about_new_messages.apply_async(args=[notify.last_notification], countdown=notify.countdown)
    r.get(on_message=notify.on_message, propagate=False)

@celery.task()
def __notify_users_about_new_messages(last_notification_str):
    users = db.session.query(User).all()
    if not users:
        return

    print("will notify ?")
    print(last_notification_str)
    last_notification = datetime.datetime.strptime(last_notification_str, '%Y-%m-%dT%H:%M:%S.%f')
    for user in users:
        topics = (db.session.query(topictracker, TopicsRead, Topic)
                    .filter(TopicsRead.user_id == user.id)
                    .filter(topictracker.c.user_id == user.id)
                    .filter(TopicsRead.topic_id == topictracker.c.topic_id)
                    .filter(Topic.id == topictracker.c.topic_id)
                    .filter(Topic.last_updated > user.lastseen)
                    .filter(Topic.last_updated > last_notification)).all()
        if not topics:
            continue
        msg = "Hello " + user.username + ",\n" + "New messages have been posted in actions forum:\n"
        for topic in topics:
            msg += "- " + topic.Topic.title  + "\n"
        msg += "forum link: https://" + current_app.config['SERVER_NAME']
    
        print("will sendng this email:")
        print(msg)
        send_async_email("new messages in actions forum", user.email, msg, None, None)

notify = notify_user()

def notify_users_about_new_messages():
    # nothing to do if celery task is already scheduled
    if notify.notification_scheduled:
        print("dont notify because already scheduled")
        return

    notify.notification_scheduled = True
    notify.countdown = current_app.config['NOTIFICATION_COUNTDOWN']
    thread = Thread(target = __thd_notify)
    thread.start()

