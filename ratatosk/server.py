# Copyright (c) 2012 Spotify AB
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

# Simple REST server that takes commands in a JSON payload
import json
import os
import re
import atexit
import mimetypes
import tornado.ioloop
import tornado.web
import tornado.httpclient
import tornado.httpserver
import luigi.scheduler as scheduler
import luigi.interface as interface
import pkg_resources
try:
    import pygraphviz
except:
    pass
import signal
from cStringIO import StringIO
from luigi.rpc import RemoteSchedulerResponder
from luigi.scheduler import PENDING, DONE, FAILED, RUNNING


def _create_scheduler():
    config = interface.get_config()
    retry_delay = config.getfloat('scheduler', 'retry-delay', 900.0)
    remove_delay = config.getfloat('scheduler', 'remove-delay', 600.0)
    worker_disconnect_delay = config.getfloat('scheduler', 'worker-disconnect-delay', 60.0)
    return scheduler.CentralPlannerScheduler(retry_delay, remove_delay, worker_disconnect_delay)


class RPCHandler(tornado.web.RequestHandler):
    """ Handle remote scheduling calls using rpc.RemoteSchedulerResponder"""
    scheduler = _create_scheduler()
    api = RemoteSchedulerResponder(scheduler)

    def get(self, method):
        payload = self.get_argument('data', default="{}")
        arguments = json.loads(payload)

        if hasattr(self.api, method):
            result = getattr(self.api, method)(**arguments)
            self.write({"response": result})  # wrap all json response in a dictionary
        else:
            self.send_error(400)

class TableVisualizeHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        client = tornado.httpclient.AsyncHTTPClient()
        # TODO: use rpc module instead of hardcoded graph
        client.fetch("http://localhost:8082/api/graph", self.in_table)

    def in_table(self, graph_response):
        if graph_response.error is not None:
            print "Got error from API server"
            graph_response.rethrow()
        if graph_response.code != 200:
            print "Got response code %s from API server" % graph_response.code
            self.send_error(graph_response.code)
        tasks = json.loads(graph_response.body)["response"]
        n_nodes = 0
        # TODO: tasks need to be grouped by sample (group_by function)
        # In other words, tasks *always* have to be associated
        # with sample names in production
        task_header = ["Project", "Flowcell", "Sample"]
        status_line = ["J.Doe_00_01", "NA", "NA"]

        colors = {PENDING: ('white', 'black'),
                  DONE: ('green', 'white'),
                  FAILED: ('red', 'white'),
                  RUNNING: ('blue', 'white'),
                  'BROKEN': ('orange', 'black'),  # external task, can't run
                  }
        for task, p in tasks.iteritems():
            selector = p['status']

            if selector == PENDING and not p['workers']:
                selector = 'BROKEN'

            label = task.replace('(', '\\n(').replace(',', ',\\n')  # force GraphViz to break lines
            taskname = task.split("(")[0]
            task_header.append(taskname)
            status_line.append(selector)


        self.write("<table border=1 cellpadding=10>\n<tr>\n")
        self.write(" ".join(["<th>{}</th>".format(x) for x in task_header]))
        self.write("\n</tr><tr>\n")
        self.write(" ".join(["<td bgcolor={}>{}</td>".format(colors.get(x, ('white', 'white'))[0], x) for x in status_line]))
        self.write("\n</tr></table>")
        
        # TODO: this code definitely should not live here:
        html_header = pkg_resources.resource_string(__name__, 'static/header.html')
        self.finish()

class VisualizeHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        client = tornado.httpclient.AsyncHTTPClient()
        # TODO: use rpc module instead of hardcoded graph
        client.fetch("http://localhost:8082/api/graph", self.on_graph)

    def on_graph(self, graph_response):
        """ TODO: clean this up using templates """

        if graph_response.error is not None:
            print "Got error from API server"
            graph_response.rethrow()
        if graph_response.code != 200:
            print "Got response code %s from API server" % graph_response.code
            self.send_error(graph_response.code)

        # TODO: figure out the interface for this

        # TODO: if there are too many nodes, we need to prune the view
        # One idea: do a Dijkstra from all running nodes. Hide all nodes
        # with distance >= 50.
        tasks = json.loads(graph_response.body)["response"]

        graphviz = pygraphviz.AGraph(directed=True, size=12)
        n_nodes = 0

        colors = {PENDING: ('white', 'black'),
                  DONE: ('green', 'white'),
                  FAILED: ('red', 'white'),
                  RUNNING: ('blue', 'white'),
                  'BROKEN': ('orange', 'black'),  # external task, can't run
                  }
        for task, p in tasks.iteritems():
            selector = p['status']

            if selector == PENDING and not p['workers']:
                selector = 'BROKEN'

            fillcolor = colors[selector][0]
            fontcolor = colors[selector][1]
            shape = 'box'
            w = None
            # Task is a unicode object representing the task_id
            if re.search('use_long_names=True', task):
                label = task.replace('(', '\\n(').replace(',', ',\\n')  # force GraphViz to break lines
            else:
                label = task.replace('(', '\\n(').replace(',', ',\\n').split('\\n')[0]
                m = re.search('target=([0-9a-zA-Z_\./\-]*),', task)
                if m and re.search('use_target_names=True', task):
                    label = os.path.basename(m.group(1))
                    # FIXME: this is arbitrary; cannot get the width to work properly in GraphViz
                    w = len(label.encode('utf-8'))/72*12
                    colors = {PENDING: ('white', 'black'),
                              DONE: ('white', 'black'),
                              FAILED: ('white', 'black'),
                              RUNNING: ('white', 'black'),
                              'BROKEN': ('organge', 'black'),  # external task, can't run
                              }
                    fillcolor = colors[selector][0]
                    fontcolor = colors[selector][1]


            # TODO: if the ( or , is a part of the argument we shouldn't really break it
            # TODO: FIXME: encoding strings is not compatible with newer pygraphviz
            if w:
                graphviz.add_node(task.encode('utf-8'), label=label.encode('utf-8'), style='filled', fillcolor=fillcolor, fontcolor=fontcolor, shape=shape, fontname='Helvetica', fontsize=11, width=w, fixedsize=True)
            else:
                graphviz.add_node(task.encode('utf-8'), label=label.encode('utf-8'), style='filled', fillcolor=fillcolor, fontcolor=fontcolor, shape=shape, fontname='Helvetica', fontsize=11)
            n_nodes += 1

        for task, p in tasks.iteritems():
            for dep in p['deps']:
                label = ""
                if re.search('use_target_names=True', task):
                    label = task.replace('(', '\\n(').replace(',', ',\\n').split('\\n')[0]
                graphviz.add_edge(dep, task, label=label)

        if n_nodes < 200:
            graphviz.layout('dot')
        else:
            # stupid workaround...
            graphviz.layout('fdp')

        s = StringIO()
        graphviz.draw(s, format='svg')
        s.seek(0)
        svg = s.read()
        # TODO: this code definitely should not live here:
        html_header = pkg_resources.resource_string(__name__, 'static/header.html')

        pattern = r'(<svg.*?)(<g id="graph[01]".*?)(</svg>)'
        mo = re.search(pattern, svg, re.S)

        self.write(''.join([html_header,
         mo.group(1),
         '<g id="viewport">',
         mo.group(2),
        '</g>',
         mo.group(3),
         "</body></html>"]))

        self.finish()


class StaticFileHandler(tornado.web.RequestHandler):
    def get(self, path):
        # TODO: this is probably not the right way to do it...
        # TODO: security
        extension = os.path.splitext(path)[1]
        if extension in mimetypes.types_map:
            self.set_header("Content-Type", mimetypes.types_map[extension])
        data = pkg_resources.resource_string(__name__, os.path.join("static", path))
        self.write(data)


def apps(debug):
    api_app = tornado.web.Application([
        (r'/api/(.*)', RPCHandler),
    ], debug=debug)

    visualizer_app = tornado.web.Application([
        (r'/static/(.*)', StaticFileHandler),
        (r'/', VisualizeHandler)
    ], debug=debug)

    table_app = tornado.web.Application([
        (r'/static/(.*)', StaticFileHandler),
        (r'/', TableVisualizeHandler)
    ], debug=debug)

    return api_app, visualizer_app, table_app


def run(visualizer_processes=1, visualizer_port=8081, api_port=8082, table_visualizer_port=8083):
    """ Runs one instance of the API server and <visualizer_processes> visualizer servers
    """
    import luigi.process as process

    api_app, visualizer_app, table_app = apps(debug=False)

    visualizer_sockets = tornado.netutil.bind_sockets(visualizer_port)
    api_sockets = tornado.netutil.bind_sockets(api_port)
    table_sockets = tornado.netutil.bind_sockets(table_visualizer_port)

    proc, attempt = process.fork_linked_workers(1 + visualizer_processes)

    if proc == 0:
        # first process is API server
        if attempt != 0:
            print "API instance died. Will not restart."
            exit(0)  # will not be restarted if it dies, as it indicates an issue that should be fixed
        print "Launching API instance"

        # load scheduler state
        RPCHandler.scheduler.load()

        # prune work DAG every 10 seconds
        pruner = tornado.ioloop.PeriodicCallback(RPCHandler.scheduler.prune, 10000)
        pruner.start()

        def shutdown_handler(foo=None, bar=None):
            print "api instance shutting down..."
            RPCHandler.scheduler.dump()
            os._exit(0)

        server = tornado.httpserver.HTTPServer(api_app)
        server.add_sockets(api_sockets)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGQUIT, shutdown_handler)
        atexit.register(shutdown_handler)

    elif proc != 0:
        # visualizers can die and will be restarted
        print "Launching Visualizer instance %d (attempt %d)" % (proc, attempt)
        server = tornado.httpserver.HTTPServer(visualizer_app)
        server.add_sockets(visualizer_sockets)

        server2 = tornado.httpserver.HTTPServer(table_app)
        server2.add_sockets(table_sockets)

    tornado.ioloop.IOLoop.instance().start()

def run_api_threaded(api_port=8082):
    ''' For unit tests'''

    api_app, visualizer_app = apps(debug=False)

    api_sockets = tornado.netutil.bind_sockets(api_port)

    server = tornado.httpserver.HTTPServer(api_app)
    server.add_sockets(api_sockets)

    def run_tornado():
        tornado.ioloop.IOLoop.instance().start()

    import threading
    threading.Thread(target=run_tornado).start()

def stop():
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == "__main__":
    run()
