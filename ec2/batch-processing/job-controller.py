#!/usr/bin/env python

import datetime
import imp
import os
import pprint
import Queue
import sys
import time

sys.path.insert(0, "..")
import RunAndMonitorEc2Inst

import ConsMt
import JobCompletionQ
import JobReqQ
import InstMonitor


def main(argv):
	try:
		ConsMt.P("Starting ...\n")
		PollJrJcMsgs()
	except KeyboardInterrupt as e:
		ConsMt.P("\nGot a keyboard interrupt. Stopping ...")


_req_q = Queue.Queue()

def PollJrJcMsgs():
	JobReqQ.PollBackground(_req_q)
	JobCompletionQ.PollBackground(_req_q)

	while True:
		with InstMonitor.IM():
			# Blocked waiting until a request is available
			#
			# Interruptable get
			#   http://stackoverflow.com/questions/212797/keyboard-interruptable-blocking-queue-in-python
			while True:
				try:
					req = _req_q.get(timeout=100000)
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
	# TODO: May want some admission control here, like one based on how many
	# free instance slots are available.

	ConsMt.P("Got a job request msg. attrs:")
	for k, v in sorted(jr.attrs.iteritems()):
		ConsMt.P("  %s:%s" % (k, v))

	ec2_type = "c3.4xlarge"

	# Pass these as the init script parameters. Decided not to use EC2 tag
	# for these, due to its limitations.
	#   http://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/allocation-tag-restrictions.html
	jr_sqs_url = jr.msg.queue_url
	jr_sqs_msg_receipt_handle = jr.msg.receipt_handle
	init_script = "acorn-server"

	# Cassandra cluster name. It's ok for multiple clusters to have the same
	# cluster_name for Cassandra. It's ok for multiple clusters to have the
	# same name as long as they don't see each other through the gossip
	# protocol.  It's even okay to use the default one: test-cluster
	#tags["cass_cluster_name"] = "acorn"

	RunAndMonitorEc2Inst.Run(
			regions = jr.attrs["regions"].split(",")
			, ec2_type = ec2_type
			, tags = jr.attrs
			, jr_sqs_url = jr_sqs_url
			, jr_sqs_msg_receipt_handle = jr_sqs_msg_receipt_handle
			, init_script = init_script)
	ConsMt.P("\n")

	# Sleep a bit so that each cluster has a unique ID, which is made of
	# current datetime
	time.sleep(1.5)


regions_all = [
		"us-east-1"
		, "us-west-1"
		, "us-west-2"
		, "eu-west-1"
		, "eu-central-1"
		, "ap-southeast-1b"
		, "ap-southeast-2"

		# Seoul. Terminates by itself. Turns out they don't have c3 instance types.
		#, "ap-northeast-2"

		, "ap-northeast-1"
		, "sa-east-1"
		]

def ProcessJobCompletion(jc):
	job_id = jc.tags["job_id"]
	ConsMt.P("Got a job completion msg. job_id:%s" % job_id)

	fn_module = "%s/../term-insts.py" % os.path.dirname(__file__)
	mod_name,file_ext = os.path.splitext(os.path.split(fn_module)[-1])
	if file_ext.lower() != '.py':
		raise RuntimeError("Unexpected file_ext: %s" % file_ext)
	py_mod = imp.load_source(mod_name, fn_module)
	getattr(py_mod, "main")([fn_module, "job_id:%s" % job_id])

	JobCompletionQ.DeleteMsg(jc)


if __name__ == "__main__":
	sys.exit(main(sys.argv))
