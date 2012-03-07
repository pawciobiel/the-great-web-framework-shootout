import sys, os, time, re, pickle
from fabric.state import env
from fabric.decorators import task, parallel
from fabric.operations import put, run, sudo
from fabric.context_managers import hide, settings
from fabric.contrib.files import exists

here = os.path.abspath(os.path.dirname(__file__))

def _median(numbers):
    numbers = sorted(numbers)
    size = len(numbers)
    if size % 2:
        return int(round(numbers[(size - 1) / 2]))
    else:
        return int(round((numbers[size/2 - 1] + numbers[size/2]) / 2))

def _average(numbers):
    return int(round(sum(numbers, 0.0) / len(numbers)))


@task
@parallel
def gohttp(run_tests=True):
    """Run the Google Go http control test."""
    INSTALL = 'golang dtach apache2-utils'
    TEST_URL = 'http://localhost:12345/'
    
    # Check the correct usage
    if not re.match(r'^test:?', sys.argv[1]):
        print '\nERROR: You must run "test" as the first task. Run "fab -l" ' \
              'for more information and a complete list of tasks.\n'
        sys.exit(1)
    
    # Get current instance info
    for instance in env.instances:
        if instance.public_dns_name == env.host:
            break
    
    with settings(hide('running', 'stdout')):
        if run('uname -m').strip() == 'x86_64':
            ARCH = '6'
        else:
            ARCH = '8'
        
        if exists('/usr/bin/' + ARCH + 'g') and exists('/usr/bin/dtach'):
            # Kill gohttp before running it again
            if int(run('ps aux | grep -c gohttp')) > 2:
                sudo('killall -9 gohttp')
        else:
            # Do installs
            sudo('add-apt-repository ppa:gophers/go')
            sudo('apt-get update')
            sudo('apt-get -y install ' + INSTALL)
    
    if run_tests is False:
        return
    
    with settings(hide('running', 'stdout')):
        # Setup test environment
        put(here, '/home/ubuntu/')
        # For good measure
        sudo('chmod -R 777 /home/ubuntu/gohttp/')
        run(ARCH + 'g -o /home/ubuntu/gohttp/http.' + ARCH + ' /home/ubuntu/gohttp/http.go')
        run(ARCH + 'l -o /home/ubuntu/gohttp/gohttp /home/ubuntu/gohttp/http.' + ARCH)
        run('dtach -n /tmp/gohttp -Ez /home/ubuntu/gohttp/gohttp')
        time.sleep(1)
    
        # Check the test url
        if run('curl %s' % TEST_URL) != "Hello World!":
            print '*' * 80
            print '*%s*' % 'INVALID WEBSERVER RESPONSE'.center(78)
            print '*' * 80
            
            raise
        
        # Run ab
        output = ''
        for i in range(env.NUM_AB_TESTS):
            output += run(
                'ab %s %s | egrep "(^Failed)|(^Non-2xx)|(^Requests)"' %
                (env.AB_FLAGS, TEST_URL)
                )
            output += '\n'
            time.sleep(1)
    
        # Terminate instance
        sudo('killall -9 gohttp')
    
    output = output.strip().split('\n')
    for line in output:
        if (line.startswith('Failed requests') or \
            line.startswith('Non-2xx responses')) and \
           not line.strip().endswith('0'):
            print '*' * 80
            print '*%s*' % 'INVALID APACHEBENCH RESPONSE'.center(78)
            print '*' * 80
            print line
            
            raise
        elif line.startswith('Requests per second'):
            env.results['hello'].append(float(re.sub('[^0-9.]', '', line)))
    
    # Get the median of all results
    result = _median(env.results['hello'])
    
    # Update the results file
    env.resultsfp.seek(0)
    results_data = pickle.loads(env.resultsfp.read())
    
    if env.command not in results_data:
        results_data[env.command] = dict()
    if instance.id not in results_data[env.command]:
        results_data[env.command][instance.id] = dict()
    
    results_data[env.command][instance.id]['hello'] = result
    results_data[env.command][instance.id]['tmpl'] = 'n/a'
    results_data[env.command][instance.id]['db'] = 'n/a'
    env.resultsfp.seek(0)
    env.resultsfp.write(pickle.dumps(results_data))
    env.resultsfp.truncate()