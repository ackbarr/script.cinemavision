import util

import os
import re
from xml.etree import ElementTree as ET


class UserContent:
    _tree = (
        'Music',
        'Trivia',
        ('Videos', (
            ('Audio Format Bumpers', (
                'Auro 3D Audio Bumpers',
                'Dolby Atmos Bumpers',
                'Dolby Digital Bumpers',
                'Dolby Digital Plus Bumpers',
                'Dolby TrueHD Bumpers',
                'DTS Bumpers',
                'DTS-HD Master Audio Bumpers',
                'DTS-X Bumpers',
                'Other',
                'THX Bumpers'
            )),
            ('Cinema Spots', (
                '3D',
                'Coming Attractions',
                'Countdowns',
                'Courtesy',
                'Feature Presentation',
                'Intermissions',
                'Theater',
                'Trivia'

            )),
            ('Ratings Bumpers', (
                'MPAA',
                'BBFC',
                'DEJUS',
                'FSK'
            )),
        ))
    )

    def __init__(self, content_dir=None, callback=None):
        self._callback = callback
        self.setupDB()
        self.musicHandler = MusicHandler(self.log)
        self.triviaDirectoryHandler = TriviaDirectoryHandler(self.log)
        self.setContentDirectoryPath(content_dir)
        self.setupContentDirectory()
        self.loadContent()

    def setupDB(self):
        try:
            util.CALLBACK = self._callback
            import database
            self.db = database
        finally:
            util.CALLBACK = None

    def log(self, msg):
        util.DEBUG_LOG(msg)

        if not self._callback:
            return

        self._callback(msg)

    def logHeading(self, heading):
        util.DEBUG_LOG('')
        util.DEBUG_LOG('[- {0} -]'.format(heading))
        util.DEBUG_LOG('')

        if not self._callback:
            return

        self._callback(None, heading)

    def setContentDirectoryPath(self, content_dir):
        self._contentDirectory = content_dir

    def _addDirectory(self, current, tree):
        if not util.vfs.exists(current):
            util.DEBUG_LOG('Creating: {0}'.format(repr(current)))
            util.vfs.mkdirs(current)

        for branch in tree:
            if isinstance(branch, tuple):
                new = util.pathJoin(current, branch[0])
                self._addDirectory(new, branch[1])
            else:
                sub = util.pathJoin(current, branch)
                if util.vfs.exists(sub):
                    continue
                util.DEBUG_LOG('Creating: {0}'.format(repr(sub)))
                util.vfs.mkdirs(sub)

    def setupContentDirectory(self):
        if not self._contentDirectory:  # or util.vfs.exists(self._contentDirectory):
            return
        self._addDirectory(self._contentDirectory, self._tree)

    def loadContent(self):
        self.loadMusic()
        self.loadTrivia()
        self.loadAudioFormatBumpers()
        self.loadCinemaSpots()
        self.loadRatingsBumpers()

    def loadMusic(self):
        self.logHeading('LOADING MUSIC')

        basePath = util.pathJoin(self._contentDirectory, 'Music')
        paths = util.vfs.listdir(basePath)

        for path in paths:
            self.musicHandler(basePath, path)

    def loadTrivia(self):
        self.logHeading('LOADING TRIVIA')

        basePath = util.pathJoin(self._contentDirectory, 'Trivia')
        paths = util.vfs.listdir(basePath)

        for sub in paths:
            path = os.path.join(basePath, sub)
            if util.isDir(path):
                fmt = 'DIR'
            elif path.lower().endswith('.zip'):
                fmt = 'ZIP'
            else:
                fmt = 'FILE'

            self.log('Processing trivia ({0}): {1}'.format(fmt, os.path.basename(path)))

            if fmt == 'FILE':
                self.triviaDirectoryHandler.getSlide(basePath, sub)
            elif fmt == 'DIR' or fmt == 'ZIP':
                self.triviaDirectoryHandler(path)

    def loadAudioFormatBumpers(self):
        self.logHeading('LOADING AUDIO FORMAT BUMPERS')

        basePath = util.pathJoin(self._contentDirectory, 'Videos', 'Audio Format Bumpers')

        self.createBumpers(basePath, self.db.AudioFormatBumpers, 'format')

    def loadCinemaSpots(self):
        self.logHeading('LOADING CINEAM SPOTS')

        basePath = util.pathJoin(self._contentDirectory, 'Videos', 'Cinema Spots')

        self.createBumpers(basePath, self.db.CinemaSpots, 'type')

    def loadRatingsBumpers(self):
        self.logHeading('LOADING RATINGS BUMPERS')

        basePath = util.pathJoin(self._contentDirectory, 'Videos', 'Ratings Bumpers')

        self.createBumpers(basePath, self.db.RatingsBumpers, 'system')

    def createBumpers(self, basePath, model, type_name):
        paths = util.vfs.listdir(basePath)

        for sub in paths:
            path = util.pathJoin(basePath, sub)
            if not util.isDir(path):
                continue

            type_ = sub.replace(' Bumpers', '')
            for v in util.vfs.listdir(path):
                name, ext = os.path.splitext(v)
                if ext not in ('.mp4'):
                    continue
                self.log('Loading {0}: [ {1} ]'.format(model.__name__, name))
                model.get_or_create(
                    path=os.path.join(path, v),
                    defaults={
                        type_name: type_,
                        'name': name,
                        'is3D': '3D' in v
                    }
                )


class MusicHandler:
    _extensions = ('.mp3', '.wav')

    def __init__(self, callback=None):
        self._callback = callback

    def __call__(self, base, path):
        p, ext = os.path.splitext(path)
        if ext.lower() in self._extensions:
            path = util.pathJoin(base, path)
            name = os.path.basename(p)
            self._callback('Loading Song: [ {0} ]'.format(name))
            self.db.Song.get_or_create(
                path=path,
                defaults={'name': name}
            )


class TriviaDirectoryHandler:
    _formatXML = 'slides.xml'
    _ratingNA = ('slide', 'rating')
    _questionNA = ('question', 'format')
    _clueNA = ('clue', 'format')
    _answerNA = ('answer', 'format')

    _imageExtensions = ('.jpg', '.png')

    def __init__(self, callback=None):
        self._callback = callback

    def __call__(self, basePath):
        slideXML = util.pathJoin(basePath, self._formatXML)
        if not util.vfs.exists(slideXML):
            return self.processSimpleDir(basePath)

        f = util.vfs.File(slideXML, 'r')
        xml = f.read()
        f.close()
        slides = ET.fromstring(xml)
        slide = slides.find('slide')
        if slide is None:
            util.LOG('BAD_SLIDE_FILE')
            return None

        rating = self.getNodeAttribute(slide, self._ratingNA[0], self._ratingNA[1]) or ''
        questionRE = (self.getNodeAttribute(slide, self._questionNA[0], self._questionNA[1]) or '').replace('N/A', '')
        clueRE = self.getNodeAttribute(slide, self._clueNA[0], self._clueNA[1]) or ''.replace('N/A', '')
        answerRE = self.getNodeAttribute(slide, self._answerNA[0], self._answerNA[1]) or ''.replace('N/A', '')

        contents = util.vfs.listdir(basePath)

        trivia = {}

        for c in contents:
            path = util.pathJoin(basePath, c)
            name = c.split('_', 1)[0]

            if name not in trivia:
                trivia[name] = {'q': '', 'c': [], 'a': ''}

            if re.search(questionRE, c):
                trivia[name]['q'] = path
            elif re.search(answerRE, c):
                trivia[name]['a'] = path
            elif re.search(clueRE, c):
                trivia[name]['c'].append(path)

        for name, data in trivia.items():
            questionPath = data['q']
            answerPath = data['a']

            if not questionPath or not answerPath:
                continue

            self._callback('Loading Trivia(QA): [ {0} ]'.format(name))

            defaults = {
                    'type': 'QA',
                    'name': name,
                    'rating': rating,
                    'questionPath': questionPath
            }

            ct = 1
            for c in data['c']:
                defaults['cluePath{0}'.format(ct)] = c
                ct += 1

            self.db.Trivia.get_or_create(
                answerPath=answerPath,
                defaults=defaults
            )

    def processSimpleDir(self, path):
        contents = util.vfs.listdir(path)
        for c in contents:
            self.getSlide(path, c)

    def getSlide(self, path, c):
        name, ext = os.path.splitext(c)
        if ext not in self._imageExtensions:
            return

        self._callback('Loading Trivia (fact): [ {0} ]'.format(name))
        self.db.Trivia.get_or_create(
                answerPath=util.pathJoin(path, c),
                defaults={
                    'type': 'fact',
                    'name': name
                }
            )

    def getNodeAttribute(self, node, sub_node_name, attr_name):
        subNode = node.find(sub_node_name)
        if subNode is not None:
            return subNode.attrib.get(attr_name)
        return None
