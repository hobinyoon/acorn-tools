import boto3
import os
import pprint
import sys
import threading

sys.path.insert(0, "%s/../util/python" % os.path.dirname(os.path.realpath(__file__)))
import Cons
import Util


_fmt = "%-15s %10s %10s %13s %15s %15s %13s %20s"
_regions_all = [
		"us-east-1"
		, "us-west-1"
		, "us-west-2"
		, "eu-west-1"
		, "eu-central-1"
		, "ap-southeast-1"
		, "ap-southeast-2"
		, "ap-northeast-2"
		, "ap-northeast-1"
		, "sa-east-1"
		]


def Run(tag_name = None):
	sys.stdout.write("desc_instances:")
	sys.stdout.flush()

	dis = []
	for r in _regions_all:
		dis.append(DescInstPerRegion(r, tag_name))

	threads = []
	for di in dis:
		t = threading.Thread(target=di.Run)
		threads.append(t)
		t.start()

	for t in threads:
		t.join()
	print ""

	num_insts = 0
	for di in dis:
		num_insts += di.NumInsts()
	if num_insts == 0:
		ConsP("No instances found.")
		return

	print ""
	ConsP(Util.BuildHeader(_fmt,
		"Placement:AvailabilityZone"
		" InstanceId"
		" InstanceType"
		" LaunchTime"
		" PrivateIpAddress"
		" PublicIpAddress"
		" State:Name"
		" Tag:Name"
		))

	for di in dis:
		di.PrintResult()


def GetPubIpAddrs(tag_name = None):
	sys.stdout.write("desc_instances:")
	sys.stdout.flush()

	dis = []
	for r in _regions_all:
		dis.append(DescInstPerRegion(r, tag_name))

	threads = []
	for di in dis:
		t = threading.Thread(target=di.Run)
		threads.append(t)
		t.start()

	for t in threads:
		t.join()
	print ""

	ip_addrs = []
	for di in dis:
		ip_addrs += di.PubIpAddrs()
	return ip_addrs


class DescInstPerRegion:
	def __init__(self, region, tag_name):
		self.region = region
		self.tag_name = tag_name
		self.exception = None

	def Run(self):
		try:
			# http://boto3.readthedocs.io/en/latest/guide/session.html
			session = boto3.session.Session()
			boto_client = session.client("ec2", region_name=self.region)

			if self.tag_name == None:
				self.response = boto_client.describe_instances()
			else:
				self.response = boto_client.describe_instances(
						Filters = [{
							'Name': 'tag:Name',
							'Values': [self.tag_name]
							}]
						)

		except KeyError as e:
			#ConsP("region=%s KeyError=[%s]" % (self.region, e))
			self.exception = e

		sys_stdout_write(" %s" % self.region)

	def NumInsts(self):
		if self.exception != None:
			return 0
		num = 0
		for r in self.response["Reservations"]:
			for r1 in r["Instances"]:
				num += 1
		return num

	def PubIpAddrs(self):
		ip_addrs = []
		if self.exception != None:
			return ip_addrs
		for r in self.response["Reservations"]:
			for r1 in r["Instances"]:
				ip_addrs.append(r1["PublicIpAddress"])
		return ip_addrs


	def PrintResult(self):
		if self.exception != None:
			ConsP("region=%s KeyError=[%s]" % (self.region, self.exception))
			return

		#ConsP(pprint.pformat(self.response, indent=2, width=100))

		for r in self.response["Reservations"]:
			for r1 in r["Instances"]:
				tag_name = None
				if "Tags" in r1:
					for t in r1["Tags"]:
						if t["Key"] == "Name":
							tag_name = t["Value"]

				ConsP(_fmt % (
					_Value(_Value(r1, "Placement"), "AvailabilityZone")
					, _Value(r1, "InstanceId")
					, _Value(r1, "InstanceType")
					, _Value(r1, "LaunchTime").strftime("%y%m%d-%H%M%S")
					, _Value(r1, "PrivateIpAddress")
					, _Value(r1, "PublicIpAddress")
					, _Value(_Value(r1, "State"), "Name")
					, tag_name
					))


def _Value(dict_, key):
	if key == "":
		return ""

	if key in dict_:
		return dict_[key]
	else:
		return ""


_print_lock = threading.Lock()

# Serialization is not needed in this file. Leave it for now.
def ConsP(msg):
	with _print_lock:
		Cons.P(msg)


def sys_stdout_write(msg):
	with _print_lock:
		sys.stdout.write(msg)
		sys.stdout.flush()

