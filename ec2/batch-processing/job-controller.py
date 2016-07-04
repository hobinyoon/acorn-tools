#!/usr/bin/env python

import imp
import json
import os
import pprint
import Queue
import sys
import time
import traceback

sys.path.insert(0, "%s/../../util/python" % os.path.dirname(__file__))
import Cons

sys.path.insert(0, "..")
import ReqSpotAndMonitor
import RunAndMonitorEc2Inst

import JobCompletionQ
import JobReqQ
import InstMonitor
import S3


def main(argv):
	try:
		Cons.P("Starting ...")
		PollJrJcMsgs()
	except KeyboardInterrupt as e:
		Cons.P("\n%s Got a keyboard interrupt. Stopping ..." % time.strftime("%y%m%d-%H%M%S"))
	except Exception as e:
		Cons.P("\n%s Got an exception: %s\n%s" % (time.strftime("%y%m%d-%H%M%S"), e, traceback.format_exc()))
	# Deleting the job request queue is useful for preventing the job request
	# reappearing

	# You can temporarily disable this for dev, but needs to be very careful. You
	# can easily spend $1000 a night.
	JobReqQ.DeleteQ()


# Not sure if a Queue is necessary when the maxsize is 1. Leave it for now.
_q_jr = Queue.Queue(maxsize=1)
_q_jc = Queue.Queue(maxsize=1)

def PollJrJcMsgs():
	JobReqQ.PollBackground(_q_jr)
	JobCompletionQ.PollBackground(_q_jc)

	while True:
		with InstMonitor.IM():
			# Blocked waiting until a request is available
			#
			# Interruptable get
			#   http://stackoverflow.com/questions/212797/keyboard-interruptable-blocking-queue-in-python
			while True:
				try:
					req = _q_jc.get(timeout=1)
					break
				except Queue.Empty:
					pass

				try:
					req = _q_jr.get(timeout=1)
					break
				except Queue.Empty:
					pass

		if isinstance(req, JobReqQ.JobReq):
			ProcessJobReq(req)
		elif isinstance(req, JobCompletionQ.JobCompleted):
			ProcessJobCompletion(req)
		else:
			raise RuntimeError("Unexpected type %s" % type(req))


def ProcessJobReq(jr):
	# Note: May want some admission control here, like one based on how many free
	# instance slots are available.

	Cons.P("\n%s Got a job request msg. attrs:\n%s"
			% (time.strftime("%y%m%d-%H%M%S"), pprint.pformat(jr.attrs)))

	# Pass these as the init script parameters. Decided not to use EC2 tag
	# for these, due to its limitations.
	#   http://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/allocation-tag-restrictions.html
	jr_sqs_url = jr.msg.queue_url
	jr_sqs_msg_receipt_handle = jr.msg.receipt_handle

	# Get job controller parameters and delete them from the attrs
	jc_params = json.loads(jr.attrs["job_controller_params"])
	jr.attrs.pop("job_controller_params", None)

	# Cassandra cluster name. It's ok for multiple clusters to have the same
	# cluster_name for Cassandra. It's ok for multiple clusters to have the
	# same name as long as they don't see each other through the gossip
	# protocol.  It's even okay to use the default one: test-cluster
	#tags["cass_cluster_name"] = "acorn"

	ReqSpotAndMonitor.Run(
			region_spot_req = jc_params["region_spot_req"]
			, tags = jr.attrs
			, jr_sqs_url = jr_sqs_url
			, jr_sqs_msg_receipt_handle = jr_sqs_msg_receipt_handle
			, init_script = jc_params["init_script"]
			)
	# On-demand instances are too expensive.
	#RunAndMonitorEc2Inst.Run()

	# No need to sleep here. Launching a cluster takes like 30 secs.  Used to
	# sleep a bit so that each cluster has a unique ID, which is made of current
	# datetime
	#time.sleep(1.5)


def ProcessJobCompletion(jc):
	job_id = jc.attrs["job_id"]
	Cons.P("\n%s Got a job completion msg. job_id:%s" % (time.strftime("%y%m%d-%H%M%S"), job_id))

	fn_module = "%s/../term-insts.py" % os.path.dirname(__file__)
	mod_name,file_ext = os.path.splitext(os.path.split(fn_module)[-1])
	if file_ext.lower() != '.py':
		raise RuntimeError("Unexpected file_ext: %s" % file_ext)
	py_mod = imp.load_source(mod_name, fn_module)
	getattr(py_mod, "main")([fn_module, "job_id:%s" % job_id])

	JobReqQ.DeleteMsg(jc.attrs["job_req_msg_recript_handle"])

	JobCompletionQ.DeleteMsg(jc)
	S3.Sync()


if __name__ == "__main__":
	sys.exit(main(sys.argv))
