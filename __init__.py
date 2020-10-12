from CTFd import utils
from CTFd.models import db, Solves, Fails, Flags, Challenges, ChallengeFiles, Tags, Hints
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import BaseChallenge, CHALLENGE_CLASSES
from CTFd.plugins.flags import get_flag_class
from CTFd.utils.config import is_teams_mode
from CTFd.utils.config.visibility import challenges_visible
from CTFd.utils.uploads import delete_file
from CTFd.utils.user import get_ip, is_admin, authed, get_current_user, get_current_team
from flask import session, abort, send_file
from io import BytesIO
import json
import logging
import os

from .config import registrar_host, registrar_port

try:
    from urllib.parse import quote
    from urllib.request import urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib import quote
    from urllib2 import urlopen, HTTPError

plugin_dirname = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger('naumachia')
registrar_timeout = 10

class NaumachiaChallengeModel(Challenges):
    __mapper_args__ = {'polymorphic_identity': 'naumachia'}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    naumachia_name = db.Column(db.String(80))

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.naumachia_name = kwargs["naumachia_name"]

class NaumachiaChallenge(BaseChallenge):
    id = "naumachia"  # Unique identifier used to register challenges
    name = "naumachia"  # Name of a challenge type
    templates = {  # Nunjucks templates used for each aspect of challenge editing & viewing
        'create': '/plugins/{0}/assets/create.html'.format(plugin_dirname),
        'update': '/plugins/{0}/assets/update.html'.format(plugin_dirname),
        'view': '/plugins/{0}/assets/view.html'.format(plugin_dirname),
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        'create': '/plugins/{0}/assets/create.js'.format(plugin_dirname),
        'update': '/plugins/{0}/assets/update.js'.format(plugin_dirname),
        'view': '/plugins/{0}/assets/view.js'.format(plugin_dirname),
    }

    # Allows the default implementations of create and delete in BaseChallenge to work here.
    challenge_model = NaumachiaChallengeModel

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        data = super().read(challenge)
        data['naumachia_name'] = challenge.naumachia_name
        return data

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()

        for attr, value in data.items():
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge

def user_can_get_config():
    if is_admin():
        return True
    if not authed():
        return False
    if not challenges_visible():
        return False
    return True

def send_config(host, escaped_chalname, escaped_clientname):
    url = "http://{0}/{1}/get?cn={2}".format(host, escaped_chalname, escaped_clientname)
    logger.debug("Requesting: {0}".format(url))
    resp = urlopen(url, timeout=registrar_timeout)
    config = json.loads(resp.read().decode('utf-8')).encode('utf-8')
    return send_file(
        BytesIO(config),
        attachment_filename="{0}.ovpn".format(escaped_chalname),
        as_attachment=True
    )

def load(app):
    app.db.create_all()
    CHALLENGE_CLASSES['naumachia'] = NaumachiaChallenge

    # Intitialize logging.
    logger.setLevel(app.config.get('LOG_LEVEL', "INFO"))

    log_dir = app.config.get('LOG_FOLDER', os.path.join(os.path.dirname(__file__), 'logs'))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'naumachia.log')

    if not os.path.exists(log_file):
        open(log_file, 'a').close()

    handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10000)
    logger.addHandler(handler)
    logger.propagate = 0

    @app.route('/naumachia/config/<int:chalid>', methods=['GET'])
    def registrar(chalid):
        if not user_can_get_config():
            logger.info("[403] Client {0} requested config for challenge {1}: Not authorized".format(session.get('clientname', '<not authed>'), chalid))
            abort(403)

        if is_teams_mode():
            clientname = get_current_team().name
        else:
            clientname = get_current_user().name

        chal = NaumachiaChallengeModel.query.filter_by(id=chalid).first_or_404()
        if chal.state == 'hidden':
            logger.info("[404] Client {0} requested config for hidden challenge {1}".format(clientname, chal.name))
            abort(404)

        escaped_clientname = quote(clientname)
        escaped_chalname = quote(chal.naumachia_name, safe='')
        host = "{0}:{1}".format(registrar_host, registrar_port)

        try:
            resp = send_config(host, escaped_chalname, escaped_clientname)
            logger.info("[200] Client {0} requested config for challenge {1}".format(clientname, chal.name))
            return resp
        except HTTPError as err:
            if err.code != 404:
                logger.info("[500] Config retrival failed for challenge {0}".format(chal.name))
                raise

        try:
            # The certs had not been generated yet. Generate them now
            url = "http://{0}/{1}/add?cn={2}".format(host, escaped_chalname, escaped_clientname)
            logger.debug("Requesting: {0}".format(url))
            urlopen(url, timeout=registrar_timeout)

            resp = send_config(host, escaped_chalname, escaped_clientname)
            logger.info("[200] Client {0} requested new config for challenge {1}".format(clientname, chal.name))
            return resp
        except HTTPError:
            logger.info("[500] Config creation failed for challenge {0}".format(chal.name))
            raise

    register_plugin_assets_directory(app, base_path='/plugins/{0}/assets/'.format(plugin_dirname))
